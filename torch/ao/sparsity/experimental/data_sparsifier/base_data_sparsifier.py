import abc
import torch
from typing import Optional, Tuple, List, Any, Dict
from ...sparsifier import base_sparsifier
from collections import defaultdict
from torch import nn
import warnings
import copy
from ...sparsifier import utils
from torch.nn.utils import parametrize

__all__ = ['BaseDataSparsifier']

EMBEDDING_TYPES = {
    nn.Embedding,
    nn.EmbeddingBag,
}

SUPPORTED_TYPES = {
    torch.Tensor,
    nn.Parameter,
    *EMBEDDING_TYPES,
}


class _Container(nn.Module):
    def __init__(self):
        super().__init__()


class BaseDataSparsifier(base_sparsifier.BaseSparsifier):
    r"""
    Base Data Sparsifier class for all Data sparsifiers.
    The abstract class accepts raw torch tensors / embedding / embedding bags (refer to SUPPORTED_TYPES above)
    to prepare for sparsification.
    In this case, mask (and parametrizations) is owned by the class and not by the user.
    Specifically, the container object inside the class maintains the mask and parametrizations of the input data

    Args:
        data_list (list of tuples)
            list of (name, data) tuples to sparsify. Lookup SUPPORTED_TYPES
            for type of data. Internally, a container module handles the data sparsification.

        defaults (dict)
            default configurations will be attached to the
            configuration. Only the keys that don't exist in the `config` will
            be updated.
    Example::

        >>> data_list = [('tensor_1', torch.randn(3,3)), ('tensor_2', torch.randn(4,4))]
        >>> defaults = {'sparsity_level': 0.7}
        >>> sparsifier = DerivedDataSparsifier(data_list = data_list, **defaults) # Some sparsifier that inherits BaseDataSparsifier
        >>> new_tensor_to_add = {'name': 'tensor_3', 'data': torch.randn(5,5), 'sparsity_level': 0.3}
        >>> sparsifier.add_data(**new_tensor_to_add)
        >>> # tensor_1 and tensor_2 will have sparsity_level of 0.7 but tensor_3 will have sparsity_level=0.3
    """
    def __init__(self, data_list: Optional[List[Tuple[str, Any]]] = None, **defaults):
        super().__init__(defaults=defaults)

        self._container = _Container()

        self.data_groups: Dict[str, Dict] = defaultdict(dict)  # name -> {**config}
        if data_list is not None:
            # add data with default config here
            [self.add_data(name, data, **self.defaults) for name, data in data_list]

    def prepare(self):
        raise NotImplementedError("this function is undefined for this class")

    def _extract_weight(self, data):
        if isinstance(data, torch.Tensor):
            return data
        elif isinstance(data, nn.Parameter):
            return data.data
        elif type(data) in EMBEDDING_TYPES:
            return data.weight.data

    def add_data(self, name: str, data, **config):
        r""" Configures and parametrizes the internal container model with name and data
        """
        assert type(data) in SUPPORTED_TYPES, \
            "specified data type not supported at the moment"
        local_args = copy.deepcopy(self.defaults)
        local_args.update(config)
        self.data_groups[name] = local_args

        weight = self._extract_weight(data)

        # Bookkeeping in the container class
        mask = local_args.get('mask', torch.ones_like(weight))
        param_class = local_args.get('parametrization', utils.FakeSparsity)  # change once public_api for utils is fixed!
        param = nn.Parameter(weight, requires_grad=False)

        if name in self.state:
            # If the named data already exists - replace
            warnings.warn("Replacing existing data of the same name. - Did you mean a different name?")
            # check if parametrized
            if parametrize.is_parametrized(self._container, name):
                # If parametrized, squash mask
                self.squash_mask(names=[name], leave_parametrized=False)
            self._container.get_parameter(name).data = weight  # overwrite the data
        else:
            setattr(self._container, name, param)
        parametrize.register_parametrization(self._container, name, param_class(mask))
        self.state[name]['mask'] = mask
        return getattr(self._container, name)

    def get_data(self, name: str, return_original: bool = True):
        r"""Returns weight tensor (or data)
        Args:
            - name: name of the data to be returned
            - return_original returns weight tensor without applying parametrization if True
                else - returns the sparsified version (parametrized)
        """
        if name not in self.data_groups:
            raise ValueError("data with specified name does not exist")

        if return_original:
            if not parametrize.is_parametrized(self._container, name):
                raise ValueError("mask squashed - original mask value does not exist")
            data = getattr(self._container.parametrizations, name).original
            return data
        else:
            return getattr(self._container, name)

    def state_dict(self):
        r"""Returns the state of the optimizer as a :class:`dict`.

        It contains:
        * state - contains name -> mask mapping.
        * data_groups - a list containing all sparsity configuration groups
            with the key name specifying the name of the data
        * container_state_dict - the state dictionary of the internal
            container model used for sparsification
        """
        return {
            'state': self.state,
            'data_groups': self.data_groups,
            '_container': self._container.state_dict()
        }

    def _load_container_from_state(self, states, data_groups, container_state_dict):
        r"""This restores the state of the container specifically based on the data present in state and data_groups
        If the data was parametrized, then the data would be added to the container and then parametrized,
        else it would just add the attribute the container.
        """
        for name, state in states.items():
            config_name = data_groups.get(name, None)
            if config_name is None:
                raise RuntimeError(f"Error loading {name}")

            # check if the data with such a name was parametrized, if so parametrize
            # otherwise just set the attribute and continue
            parametrized_name = f'parametrizations.{name}.original'
            parametrized = False
            data = container_state_dict.get(name, None)
            if name in container_state_dict:
                # the parametrization was probably removed for this
                data = container_state_dict.get(name)

            elif parametrized_name in container_state_dict:
                # so the weight was parametrized
                data = container_state_dict.get(parametrized_name)
                parametrized = True

            else:
                raise RuntimeError(f"Error loading {name}")

            param = nn.Parameter(data, requires_grad=False)
            setattr(self._container, name, param)

            if parametrized:
                # register parameter if parametrized
                mask = state.get('mask', torch.ones_like(data))
                param_class = data_groups.get('parametrization', utils.FakeSparsity)  # change once public_api for utils is fixed!
                parametrize.register_parametrization(self._container, name, param_class(mask))

    def load_state_dict(self, state_dict, strict=True):
        r"""The load_state_dict() restores the state of the sparsifier based on the state_dict

        Args:
        * state_dict - the dictionary that to which the current sparsifier needs to be restored to
        * strict - If True - the sparsifier is reset and is restored exactly to the state in state_dict.
            If False - the current sparsifier is not reset before loading the state_dict i.e. data added
            before loading the state_dict is not erased.
        """
        states = copy.deepcopy(state_dict['state'])
        data_groups = copy.deepcopy(state_dict['data_groups'])
        container_state_dict = copy.deepcopy(state_dict['_container'])
        if strict:
            # if strict load -> then reset container
            self._container = _Container()

        self._load_container_from_state(states, data_groups, container_state_dict)

        if not strict:
            states.update(self.state)
            data_groups.update(self.data_groups)

        self.__setstate__({'state': states, 'data_groups': data_groups})

    def __setstate__(self, state):
        if '_container' in state:  # If container object is in state then load model
            container_dict = state.pop('_container')
            self._container = _Container()
            self._load_container_from_state(state['state'], state['data_groups'], container_dict)

        self.__dict__.update(state)

    def __getstate__(self):
        return {
            'defaults': self.defaults,
            'state': self.state,
            'data_groups': self.data_groups,
            '_container': self._container.state_dict()
        }

    def __repr__(self):
        format_string = self.__class__.__name__ + ' ('
        for name, sparse_args in self.data_groups.items():
            format_string += '\n'
            format_string += '\tData Group\n'
            format_string += f'\t    name: {name}\n'
            for key in sorted(sparse_args.keys()):
                if key == 'data':
                    continue
                format_string += f'\t    {key}: {sparse_args[key]}\n'
        format_string += ')'
        return format_string

    def get_mask(self, name: str):
        if name not in self.state:
            raise ValueError("data with specified name does not exist")
        return self.state[name]['mask']

    def squash_mask(self, *args, leave_parametrized=True, names=None, **kwargs):
        r"""Squashes the sparse masks into the appropriate tensors. Also, accepts list of strings
        to squash mask for. If none, squashes mask for all the keys
        kwargs:
            * names: list of strings to squash mask for
            * sparsified: if true - applies the mask before squashing
                          if false - does not apply the mask before squashing
        """
        if names is None:
            names = list(self.data_groups.keys())
        for name in names:
            parametrize.remove_parametrizations(self._container, name, leave_parametrized=leave_parametrized)

    def step(self):
        if not self.enable_mask_update:
            return
        with torch.no_grad():
            for name, config in self.data_groups.items():
                # get non-sparsified data
                data = self.get_data(name)
                # need name for the mask otherwise can directly pass mask?
                self.update_mask(name, data, **config)

    @abc.abstractmethod
    def update_mask(self, name, data, **kwargs):
        pass

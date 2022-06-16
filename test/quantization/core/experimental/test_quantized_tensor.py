# Owner(s): ["oncall: quantization"]

import torch
from torch import quantize_per_tensor
from torch.ao.quantization.experimental.APoT_tensor import TensorAPoT
import unittest
import random
quantize_APoT = TensorAPoT.quantize_APoT
dequantize = TensorAPoT.dequantize

class TestQuantizedTensor(unittest.TestCase):
    """ Tests quantize_APoT result on random 1-dim tensor
        and hardcoded values for b, k by comparing to uniform observer
        quantized tensor (https://pytorch.org/docs/stable/generated/torch.quantize_per_tensor.html)
        * tensor2quantize: Tensor
        * b: 4
        * k: 2
    """
    def test_quantize_APoT_rand_1d(self):
        # generate random size of tensor2dequantize between 1 -> 16
        # because there are 2**b = 2**4 quantization levels total
        size = random.randint(1, 16)

        # generate tensor with random fp values between 0 -> 1
        tensor2quantize = torch.rand(size)

        apot_quantized = TensorAPoT(4, 2, False)

        # get apot quantized tensor result
        apot_quantized = apot_quantized.quantize_APoT(tensor2quantize=tensor2quantize)

        # get uniform observer quantized tensor result
        uniform_quantized = quantize_per_tensor(input=tensor2quantize, scale=1.0, zero_point=0, dtype=torch.quint8).int_repr()

        apot_quantized_tens = torch.tensor(apot_quantized.data).type(torch.uint8)
        uniform_quantized_tens = uniform_quantized.data

        self.assertTrue(torch.equal(apot_quantized_tens, uniform_quantized_tens))

    """ Tests quantize_APoT result on random 2-dim tensor
        and hardcoded values for b, k by comparing to uniform observer
        quantized tensor (https://pytorch.org/docs/stable/generated/torch.quantize_per_tensor.html)
        * tensor2quantize: Tensor
        * b: 6
        * k: 2
    """
    def test_quantize_APoT_rand_2d(self):
        # generate random size of tensor2dequantize between 1 -> 64
        # because there are 2**b = 2**6 quantization levels total
        size = random.randint(1, 64)

        # generate tensor with random fp values between 0 -> 1
        tensor2quantize = torch.rand(size, size)

        apot_quantized = TensorAPoT(6, 2, False)

        # get apot quantized tensor result
        apot_quantized = apot_quantized.quantize_APoT(tensor2quantize=tensor2quantize)

        # get uniform observer quantized tensor result
        uniform_quantized = quantize_per_tensor(input=tensor2quantize, scale=1.0, zero_point=0, dtype=torch.quint8).int_repr()

        apot_quantized_tens = torch.tensor(apot_quantized.data).type(torch.uint8)
        uniform_quantized_tens = uniform_quantized.data

        self.assertTrue(torch.equal(apot_quantized_tens, uniform_quantized_tens))

    """ Tests quantize_apot result on random 1-dim tensor
        and hardcoded values for b, k
        * tensor2quantize: Tensor
        * b: 4
        * k: 2
    """
    def test_dequantize_APoT_ramd_1d(self):
        # generate random size of tensor2dequantize
        size = random.randint(1, 16)

        # generate tensor with random values between 0 -> 2**4 = 16
        # because there are 2**b = 2**4 quantization levels total
        tensor2dequantize = 16 * torch.rand(size)

        tensor2dequantize = tensor2dequantize.int()

        orig_input = tensor2dequantize.clone()

        max_val = torch.max(orig_input)

        tensor2dequantize = dequantize(tensor2dequantize, 4, 2)

        # make observer
        obs = APoTObserver(max_val=max_val, b=4, k=2)
        obs_result = obs.calculate_qparams(signed=False)

        quantized_levels = obs_result[1]
        level_indices = obs_result[2]

        input_arr = list(orig_input)
        result_arr = list(tensor2dequantize)

        zipped_result = zip(input_arr, result_arr)

        expected_result = True

        for ele, res in zipped_result:
            idx = list(level_indices).index(ele)
            if res != quantized_levels[idx]:
                expected_result = False

        self.assertTrue(expected_result)

    """ Tests quantize_apot result on random 2-dim tensor
        and hardcoded values for b, k
        * tensor2quantize: Tensor
        * b: 6
        * k: 2
    """
    def test_dequantize_APoT_ramd_2d(self):
        # generate random size of tensor2dequantize
        size1 = random.randint(1, 64)
        size2 = random.randint(1, 64)

        # generate tensor with random values between 0 -> 2**6 = 64
        # because there are 2**b = 2**6 quantization levels total
        tensor2dequantize = 64 * torch.rand(size1, size2)

        tensor2dequantize = tensor2dequantize.int()

        orig_input = tensor2dequantize.clone()

        max_val = torch.max(orig_input)

        tensor2dequantize = dequantize(tensor2dequantize, 6, 2)

        # make observer
        obs = APoTObserver(max_val=max_val, b=6, k=2)
        obs_result = obs.calculate_qparams(signed=False)

        quantized_levels = obs_result[1]
        level_indices = obs_result[2]

        input_arr = list(orig_input.flatten())
        result_arr = list(tensor2dequantize.flatten())

        zipped_result = zip(input_arr, result_arr)

        expected_result = True

        for ele, res in zipped_result:
            idx = list(level_indices).index(ele)
            if res != quantized_levels[idx]:
                expected_result = False

        self.assertTrue(expected_result)

    """ Tests quantize_apot result on random 3-dim tensor
        and hardcoded values for b, k
        * tensor2quantize: Tensor
        * b: 6
        * k: 2
    """
    def test_dequantize_APoT_ramd_3d(self):
        # generate random size of tensor2dequantize
        size1 = random.randint(1, 64)
        size2 = random.randint(1, 64)
        size3 = random.randint(1, 64)

        # generate tensor with random values between 0 -> 2**6 = 64
        # because there are 2**b = 2**6 quantization levels total
        tensor2dequantize = 64 * torch.rand(size1, size2, size3)

        tensor2dequantize = tensor2dequantize.int()

        orig_input = tensor2dequantize.clone()

        max_val = torch.max(orig_input)

        tensor2dequantize = dequantize(tensor2dequantize, 6, 2)

        # make observer
        obs = APoTObserver(max_val=max_val, b=6, k=2)
        obs_result = obs.calculate_qparams(signed=False)

        quantized_levels = obs_result[1]
        level_indices = obs_result[2]

        input_arr = list(orig_input.flatten())
        result_arr = list(tensor2dequantize.flatten())

        zipped_result = zip(input_arr, result_arr)

        expected_result = True

        for ele, res in zipped_result:
            idx = list(level_indices).index(ele)
            if res != quantized_levels[idx]:
                expected_result = False

        self.assertTrue(expected_result)

    def test_q_apot_alpha(self):
        with self.assertRaises(NotImplementedError):
            TensorAPoT.q_apot_alpha(self)

if __name__ == '__main__':
    unittest.main()

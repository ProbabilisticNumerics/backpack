import functools

import torch

from backpack.utils.einsum import einsum


def new_output_convention(old_mat, module):
    print("[to new]: in  {}".format(old_mat.shape))
    N = module.output_shape[0]
    V = old_mat.shape[-1]
    # (C_out, H_out, W_out, ...)
    out_features_shape = module.output_shape[1:]
    # C_out * H_out * W_out * ...
    out_features = torch.prod(out_features_shape)

    # [N, C_out * H_out * W_out, V]
    assert old_mat.shape == (N, out_features, V)
    # [V, N, C_out * H_out * W_out]
    new_mat = einsum("ndv->vnd", old_mat)
    # [V, N, C_out, H_out, W_out, ...]
    new_shape = (V, N) + tuple(out_features_shape)
    new_mat = new_mat.reshape(new_shape)

    print("[to new]: out {}".format(new_mat.shape))

    return new_mat


def _new_param_convention(old_mat, module, sum_batch, name):
    print("[to old]: in  {}".format(old_mat.shape))
    V = old_mat.shape[-1]
    N = old_mat.shape[0]

    param = getattr(module, name)
    param_numel = param.numel()

    if sum_batch:
        assert old_mat.shape == (param_numel, V)
    else:
        assert old_mat.shape == (N, param_numel, V)

    # move V to first dimension
    new_mat = einsum("...v->v...", old_mat)

    param_shape = tuple(param.shape)
    if sum_batch:
        out_shape = (V,) + param_shape
    else:
        out_shape = (V, N) + param_shape

    return new_mat.view(out_shape)


def new_weight_convention(old_mat, module, sum_batch):
    return _new_param_convention(old_mat, module, sum_batch, "weight")


def new_bias_convention(old_mat, module, sum_batch):
    return _new_param_convention(old_mat, module, sum_batch, "bias")


def _old_param_convention(new_mat, module, sum_batch, name):
    print("[to old]: in  {}".format(new_mat.shape))
    V = new_mat.shape[0]
    N = new_mat.shape[1]

    param = getattr(module, name)

    param_shape = tuple(param.shape)

    if sum_batch:
        assert new_mat.shape == (V,) + param_shape
    else:
        assert new_mat.shape == (V, N) + param_shape

    param_numel = param.numel()

    if sum_batch:
        out_shape = (V, param_numel)
    else:
        out_shape = (V, N, param_numel)

    old_mat = new_mat.reshape(out_shape)

    if sum_batch:
        equation = "vi->iv"
    else:
        equation = "vni->niv"

    return einsum(equation, old_mat)


def old_weight_convention(new_mat, module, sum_batch):
    return _old_param_convention(new_mat, module, sum_batch, "weight")


def old_bias_convention(new_mat, module, sum_batch):
    return _old_param_convention(new_mat, module, sum_batch, "bias")


def new_input_convention(old_mat, module):
    print("[to new]: in  {}".format(old_mat.shape))
    N = module.input0_shape[0]
    V = old_mat.shape[-1]
    # (C_in, H_in, W_in, ...)
    in_features_shape = module.input0_shape[1:]
    # C_in * H_in * W_in * ...
    in_features = torch.prod(in_features_shape)

    # [N, C_in * H_in * W_in, V]
    assert old_mat.shape == (N, in_features, V)
    # [V, N, C_in * H_in * W_in]
    new_mat = einsum("ndv->vnd", old_mat)
    # [V, N, C_in, H_in, W_in, ...]
    new_shape = (V, N) + tuple(in_features_shape)
    new_mat = new_mat.reshape(new_shape)

    print("[to new]: out {}".format(new_mat.shape))

    return new_mat


def old_input_convention(new_mat, module):
    print("[to old]: in  {}".format(new_mat.shape))
    N = module.input0_shape[0]
    V = new_mat.shape[0]
    # (C_in, H_in, W_in, ...)
    in_features_shape = module.input0_shape[1:]
    # C_in * H_in * W_in * ...
    in_features = torch.prod(in_features_shape)

    # [V, N, C_in, H_in, W_in]
    assert new_mat.shape == (V, N) + tuple(in_features_shape)
    # [V, N, C_in* H_in* W_in]
    old_mat = new_mat.reshape((V, N, in_features))
    # [N, C_in* H_in* W_in, V]
    old_mat = einsum("vnc->ncv", old_mat)

    print("[to old]: out {}".format(old_mat.shape))

    return old_mat


def old_output_convention(new_mat, module):
    print("[to old]: in  {}".format(new_mat.shape))
    N = module.output_shape[0]
    V = new_mat.shape[0]
    # (C_out, H_out, W_out, ...)
    out_features_shape = module.output_shape[1:]
    # C_out * H_out * W_out * ...
    out_features = torch.prod(out_features_shape)

    # [V, N, C_out, H_out, W_out]
    assert new_mat.shape == (V, N) + tuple(out_features_shape)
    # [V, N, C_out* H_out* W_out]
    old_mat = new_mat.reshape((V, N, out_features))
    # [N, C_out* H_out* W_out, V]
    old_mat = einsum("vnc->ncv", old_mat)

    print("[to old]: out {}".format(old_mat.shape))

    return old_mat


def add_V_dim(old_mat):
    return old_mat.unsqueeze(-1)


def add_V_dim_new_convention(mat):
    return mat.unsqueeze(0)


def remove_V_dim_new_convention(mat):
    return mat.squeeze(0)


def remove_V_dim(old_mat):
    return old_mat.squeeze(-1)


def jac_t_new_shape_convention(jmp):
    """Use new convention internally, old convention for IO."""

    @functools.wraps(jmp)
    def wrapped_jac_t_use_new_convention(self, module, g_inp, g_out, mat, **kwargs):
        print("[jac_t]")
        # [N, D, V]
        is_vec = len(mat.shape) == 2
        print(is_vec)
        mat_used = mat if not is_vec else add_V_dim(mat)

        # convert and run with new convention
        mat_used = new_output_convention(mat_used, module)
        result = jmp(self, module, g_inp, g_out, mat_used, **kwargs)
        result = old_input_convention(result, module)

        result = result if not is_vec else remove_V_dim(result)

        return result

    return wrapped_jac_t_use_new_convention


def check_like_and_is_vec(mat_shape, like_shape):
    is_vec, fail = None, None
    if len(mat_shape) == len(like_shape):
        is_vec = True
        if not (mat_shape == like_shape):
            fail = True
    elif len(mat_shape) - len(like_shape) == 1:
        is_vec = False
        if not (mat_shape[1:] == like_shape):
            fail = True
    else:
        fail = True

    if fail:
        raise ValueError(
            "Accept {} or {}, got {}".format(like_shape, [-1, *like_shape], mat_shape)
        )

    return is_vec


def check_like_output_and_is_vec(module, mat):
    mat_shape = [int(dim) for dim in mat.shape]
    out_shape = [int(dim) for dim in module.output_shape]

    return check_like_and_is_vec(mat_shape, out_shape)


def check_like_input_and_is_vec(module, mat):
    mat_shape = [int(dim) for dim in mat.shape]
    in_shape = [int(dim) for dim in module.input0_shape]

    return check_like_and_is_vec(mat_shape, in_shape)


def check_like_param_and_is_vec(module, mat, sum_batch, name):
    mat_shape = [int(dim) for dim in mat.shape]
    param_shape = [int(dim) for dim in getattr(module, name).shape]

    N = int(module.output_shape[0])
    out_shape = param_shape if sum_batch else [N, *param_shape]

    return check_like_and_is_vec(mat_shape, out_shape)


def param_jac_t_mat_prod_accept_vectors(jac_t_mat_prod, name):
    @functools.wraps(jac_t_mat_prod)
    def wrapped_param_jac_t_mat_prod(self, module, g_inp, g_out, mat, **kwargs):

        is_vec = check_like_output_and_is_vec(module, mat)
        mat_used = mat if not is_vec else add_V_dim_new_convention(mat)

        result = jac_t_mat_prod(self, module, g_inp, g_out, mat_used, **kwargs)

        sum_batch = kwargs.get("sum_batch", True)
        check_like_param_and_is_vec(module, result, sum_batch, name)

        result = result if not is_vec else remove_V_dim_new_convention(result)

        return result

    return wrapped_param_jac_t_mat_prod


def weight_jac_t_mat_prod_accept_vectors(jac_t_mat_prod):
    return param_jac_t_mat_prod_accept_vectors(jac_t_mat_prod, "weight")


def bias_jac_t_mat_prod_accept_vectors(jac_t_mat_prod):
    return param_jac_t_mat_prod_accept_vectors(jac_t_mat_prod, "bias")


def param_jac_mat_prod_accept_vectors(jac_mat_prod, name):
    @functools.wraps(jac_mat_prod)
    def wrapped_param_jac_mat_prod(self, module, g_inp, g_out, mat, **kwargs):
        sum_batch = True
        is_vec = check_like_param_and_is_vec(module, mat, sum_batch, name)

        mat_used = mat if not is_vec else add_V_dim_new_convention(mat)
        result = jac_mat_prod(self, module, g_inp, g_out, mat_used, **kwargs)
        check_like_output_and_is_vec(module, result)

        result = result if not is_vec else remove_V_dim_new_convention(result)

        return result

    return wrapped_param_jac_mat_prod


def weight_jac_mat_prod_accept_vectors(jac_mat_prod):
    return param_jac_mat_prod_accept_vectors(jac_mat_prod, "weight")


def bias_jac_mat_prod_accept_vectors(jac_mat_prod):
    return param_jac_mat_prod_accept_vectors(jac_mat_prod, "bias")


def jac_t_mat_prod_accept_vectors(jac_t_mat_prod):
    @functools.wraps(jac_t_mat_prod)
    def wrapped_jac_t_mat_prod(self, module, g_inp, g_out, mat, **kwargs):

        is_vec = check_like_output_and_is_vec(module, mat)
        mat_used = mat if not is_vec else add_V_dim_new_convention(mat)

        result = jac_t_mat_prod(self, module, g_inp, g_out, mat_used, **kwargs)

        check_like_input_and_is_vec(module, result)

        result = result if not is_vec else remove_V_dim_new_convention(result)

        return result

    return wrapped_jac_t_mat_prod


def jac_mat_prod_accept_vectors(jac_mat_prod):
    @functools.wraps(jac_mat_prod)
    def wrapped_jac_mat_prod(self, module, g_inp, g_out, mat, **kwargs):
        is_vec = check_like_input_and_is_vec(module, mat)
        mat_used = mat if not is_vec else add_V_dim_new_convention(mat)

        result = jac_mat_prod(self, module, g_inp, g_out, mat_used, **kwargs)

        check_like_output_and_is_vec(module, result)

        result = result if not is_vec else remove_V_dim_new_convention(result)

        return result

    return wrapped_jac_mat_prod


def hessian_matrix_product_accept_vectors(hessian_matrix_product):
    @functools.wraps(hessian_matrix_product)
    def wrapped_hessian_matrix_product(self, module, g_inp, g_out, **kwargs):

        hmp = hessian_matrix_product(self, module, g_inp, g_out)

        def new_hmp(mat):
            is_vec = check_like_input_and_is_vec(module, mat)
            mat_used = mat if not is_vec else add_V_dim_new_convention(mat)

            result = hmp(mat_used)

            check_like_input_and_is_vec(module, result)

            result = result if not is_vec else remove_V_dim_new_convention(result)

            return result

        return new_hmp

    return wrapped_hessian_matrix_product


def CMP_in_accept_vectors(module):
    def wrapped_CMP_in_accept_vectors(CMP_in):
        @functools.wraps(CMP_in)
        def wrapped_CMP_in(mat):
            is_vec = check_like_input_and_is_vec(module, mat)
            mat_used = mat if not is_vec else add_V_dim_new_convention(mat)

            result = CMP_in(mat_used)

            check_like_input_and_is_vec(module, result)

            result = result if not is_vec else remove_V_dim_new_convention(result)

            return result

        return wrapped_CMP_in

    return wrapped_CMP_in_accept_vectors


def param_CMP_accept_vectors(module, name):
    def wrapped_param_CMP_accept_vectors(param_cmp):
        @functools.wraps(param_cmp)
        def wrapped_param_cmp(mat):
            sum_batch = True
            is_vec = check_like_param_and_is_vec(module, mat, sum_batch, name)

            mat_used = mat if not is_vec else add_V_dim_new_convention(mat)
            result = param_cmp(mat_used)

            check_like_param_and_is_vec(module, result, sum_batch, name)

            result = result if not is_vec else remove_V_dim_new_convention(result)

            return result

        return wrapped_param_cmp

    return wrapped_param_CMP_accept_vectors


def weight_CMP_accept_vectors(module):
    return param_CMP_accept_vectors(module, "weight")


def bias_CMP_accept_vectors(module):
    return param_CMP_accept_vectors(module, "bias")


def bias_jac_t_new_shape_convention(jmp):
    """Use new convention internally, old convention for IO."""

    @functools.wraps(jmp)
    def wrapped_bias_jac_t_use_new_convention(
        self, module, g_inp, g_out, mat, **kwargs
    ):
        print("[bias_jac_t]")
        # [N, D, V]
        is_vec = len(mat.shape) == 2
        print(is_vec)
        mat_used = mat if not is_vec else add_V_dim(mat)

        # convert and run with new convention
        mat_used = new_output_convention(mat_used, module)
        result = jmp(self, module, g_inp, g_out, mat_used, **kwargs)

        try:
            sum_batch = kwargs["sum_batch"]
        except KeyError:
            sum_batch = True

        result = old_bias_convention(result, module, sum_batch)

        result = result if not is_vec else remove_V_dim(result)

        return result

    return wrapped_bias_jac_t_use_new_convention


def weight_jac_new_shape_convention(jmp):
    """Use new convention internally, old convention for IO."""

    @functools.wraps(jmp)
    def wrapped_weight_jac_use_new_convention(
        self, module, g_inp, g_out, mat, **kwargs
    ):
        print("[weight_jac]")
        # [D, V]
        is_vec = len(mat.shape) == 1
        print(is_vec)
        mat_used = mat if not is_vec else add_V_dim(mat)

        # convert and run with new convention
        sum_batch = True
        mat_used = new_weight_convention(mat_used, module, sum_batch)
        result = jmp(self, module, g_inp, g_out, mat_used, **kwargs)

        result = old_output_convention(result, module)

        result = result if not is_vec else remove_V_dim(result)

        return result

    return wrapped_weight_jac_use_new_convention


def bias_jac_new_shape_convention(jmp):
    """Use new convention internally, old convention for IO."""

    @functools.wraps(jmp)
    def wrapped_bias_jac_use_new_convention(self, module, g_inp, g_out, mat, **kwargs):
        print("[bias_jac]")
        # [D, V]
        is_vec = len(mat.shape) == 1
        print(is_vec)
        mat_used = mat if not is_vec else add_V_dim(mat)

        # convert and run with new convention
        sum_batch = True
        mat_used = new_bias_convention(mat_used, module, sum_batch)
        result = jmp(self, module, g_inp, g_out, mat_used, **kwargs)

        result = old_output_convention(result, module)

        result = result if not is_vec else remove_V_dim(result)

        return result

    return wrapped_bias_jac_use_new_convention


def jac_new_shape_convention(jmp):
    """Use new convention internally, old convention for IO."""

    @functools.wraps(jmp)
    def wrapped_jac_use_new_convention(self, module, g_inp, g_out, mat, **kwargs):
        print("[jac]")
        # [N, D, V]
        is_vec = len(mat.shape) == 2
        print(is_vec)
        mat_used = mat if not is_vec else add_V_dim(mat)

        # convert and run with new convention
        mat_used = new_input_convention(mat_used, module)
        result = jmp(self, module, g_inp, g_out, mat_used, **kwargs)
        result = old_output_convention(result, module)

        result = result if not is_vec else remove_V_dim(result)

        return result

    return wrapped_jac_use_new_convention


def hessian_new_shape_convention(h_func):
    """Use new convention internally, old convention for IO."""

    @functools.wraps(h_func)
    def wrapped_h_use_new_convention(*args, **kwargs):
        print("[hessian]")

        result = h_func(*args, **kwargs)

        return einsum("cni->nic", result)

    return wrapped_h_use_new_convention


def hessian_old_shape_convention(h_func):
    """Use old convention internally, new convention for IO."""

    @functools.wraps(h_func)
    def wrapped_h_use_old_convention(*args, **kwargs):
        print("[hessian]")

        result = h_func(*args, **kwargs)

        return einsum("nic->cni", result)

    return wrapped_h_use_old_convention


def hmp_new_shape_convention(hmp_func):
    """Use new convention internally, old convention for IO."""

    @functools.wraps(hmp_func)
    def wrapped_hmp_use_new_convention(mat):
        print("[hessian]")

        mat = einsum("nic->cni", mat)

        result = hmp_func(mat)

        return einsum("cni->nic", result)

    return wrapped_hmp_use_new_convention

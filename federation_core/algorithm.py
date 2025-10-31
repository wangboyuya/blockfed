# algorithm.py
import copy
import logging
import random
import time
import torch
import math
import os
from itertools import permutations, combinations
import train
import test
from models.ResNet8 import ResNet8
from device import device


def get_clients(epoch, handle):
    agent_name_keys = handle.namelist
    handle.logger.info(f'Server Epoch:{epoch} choose agents : {agent_name_keys}.')
    return agent_name_keys


def Aggregation(w_ori, w_list, lens, beta, eta, defence_method, params):
    """优化聚合函数，使用向量化操作减少循环"""
    keys = [k for k in w_ori.keys() if w_ori[k].dtype != torch.int64]

    with torch.no_grad():
        weighted_diffs = []
        for i in range(len(w_list)):
            diff_dict = {}
            for k in keys:
                diff_dict[k] = (w_list[i][k] - w_ori[k]) * beta[i]
            weighted_diffs.append(diff_dict)

        w_avg = {}
        for k in keys:
            stacked = torch.stack([wd[k] for wd in weighted_diffs])
            w_avg[k] = torch.mean(stacked, dim=0)

        for k in keys:
            w_ori[k] += eta * w_avg[k]

    return w_ori


def calculate_model_accuracy(model_state_dict, handle):
    """计算模型在测试集上的准确率"""
    model = copy.deepcopy(handle.model)
    model.load_state_dict(model_state_dict)
    model.eval()

    correct = 0
    total = 0
    with torch.no_grad():
        for data, target in handle.test_data:
            data, target = data.to(device), target.to(device)
            outputs = model(data)
            _, predicted = torch.max(outputs.data, 1)
            total += target.size(0)
            correct += (predicted == target).sum().item()

    return correct / total


def fed_avg_aggregation(model_list):
    """联邦平均聚合"""
    if not model_list:
        return {}

    aggregated_model = {}

    # 对所有模型的权重求平均
    for key in model_list[0].keys():
        if model_list[0][key].dtype != torch.int64:  # 跳过整数类型参数
            # 堆叠所有权重并求平均
            weights_stack = torch.stack([model[key].float() for model in model_list])
            aggregated_model[key] = torch.mean(weights_stack, dim=0)
        else:
            # 对于整数参数，直接复制第一个模型的
            aggregated_model[key] = model_list[0][key].clone()

    return aggregated_model


def calculate_shapley_values(handle, w_locals, active_users, w_global):
    """计算Shapley值贡献度 - 基于排列的经典方法"""
    num_users = len(active_users)
    shapley_values = {user_id: 0.0 for user_id in active_users}

    handle.logger.info(f"开始计算Shapley值，用户数: {num_users}")

    # 生成所有排列 (最多5! = 120种排列)
    all_permutations = list(permutations(active_users))
    handle.logger.info(f"生成了 {len(all_permutations)} 种排列")

    for perm_idx, perm in enumerate(all_permutations):
        if perm_idx % 20 == 0:  # 每20种排列记录一次进度
            handle.logger.info(f"Shapley计算进度: {perm_idx}/{len(all_permutations)}")

        current_model = copy.deepcopy(w_global)
        current_performance = 0.0  # 空集的性能为0

        for i, user_id in enumerate(perm):
            # 获取当前用户的模型权重
            user_idx = active_users.index(user_id)
            user_model = w_locals[user_idx]

            # 创建包含前i+1个用户的模型
            subset_indices = [active_users.index(uid) for uid in perm[:i + 1]]
            subset_models = [copy.deepcopy(w_locals[idx]) for idx in subset_indices]
            subset_model = fed_avg_aggregation(subset_models)

            # 计算子集性能
            subset_performance = calculate_model_accuracy(subset_model, handle)

            # 计算边际贡献
            marginal_contribution = subset_performance - current_performance

            # 累加到Shapley值
            shapley_values[user_id] += marginal_contribution

            # 更新当前性能
            current_performance = subset_performance

    # 标准化Shapley值
    for user_id in shapley_values:
        shapley_values[user_id] /= len(all_permutations)

    # 归一化到[0,1]范围
    total_shapley = sum(shapley_values.values())
    if total_shapley > 0:
        for user_id in shapley_values:
            shapley_values[user_id] /= total_shapley

    handle.logger.info(f"Shapley值计算完成: {shapley_values}")
    return shapley_values


def evaluate_contribution(handle, epoch, active_users, w_locals, w_glob, previous_w_glob):
    """执行贡献度评估 - 使用Shapley值方法"""
    if len(active_users) < 2:
        handle.logger.info("参与用户不足，跳过贡献度评估")
        return

    handle.logger.info(f"开始第 {epoch} 轮贡献度评估，参与用户: {active_users}")

    try:
        # 使用Shapley值计算函数
        user_contributions = calculate_shapley_values(handle, w_locals, active_users, w_glob)

        # 记录贡献度
        handle.contribution_manager.record_round_contribution(epoch, user_contributions)

        handle.logger.info(f"第 {epoch} 轮贡献度评估完成: {user_contributions}")

    except Exception as e:
        handle.logger.error(f"贡献度计算错误: {e}")
        # 后备方案：平均分配
        user_contributions = {user_id: 1.0 / len(active_users) for user_id in active_users}
        handle.contribution_manager.record_round_contribution(epoch, user_contributions)
        handle.logger.info(f"使用平均分配作为后备方案: {user_contributions}")


def save_global_model(handle, epoch):
    """保存全局模型，每100轮保存一次，只保留一个模型"""
    if epoch % 100 == 0:
        try:
            # 确保保存目录存在
            os.makedirs(handle.folder_path, exist_ok=True)

            # 模型文件路径
            model_path = os.path.join(handle.folder_path, "global_model.pth")

            # 保存模型状态字典
            torch.save({
                'epoch': epoch,
                'model_state_dict': handle.model.state_dict(),
                'task_id': handle.task_id,
                'task_name': handle.name
            }, model_path)

            handle.logger.info(f"第 {epoch} 轮全局模型已保存到: {model_path}")

        except Exception as e:
            handle.logger.error(f"保存模型失败: {e}")


def FedAvg(handle):
    handle.model.to(device)

    for epoch in range(handle.start_epoch, handle.params['epochs'] + 1):
        if handle.params['lr_decay'] is True:
            if epoch % handle.params['lr_decay_epoch'] == 0:
                handle.params['lr'] = handle.params['lr'] * handle.params['lr_decay_gamma']
                handle.params['poison_lr'] = handle.params['poison_lr'] * handle.params['lr_decay_gamma']

        start_time = time.time()
        agent_name_keys = get_clients(epoch, handle)
        lens = len(agent_name_keys)

        beta = [1] * lens
        ori_weight = handle.model.state_dict()
        w_locals = []

        for client in agent_name_keys:
            model_copy = copy.deepcopy(handle.model)
            w = train.standard_train(epoch, handle.clients_data_num[client], client, handle.params,
                                     model_copy.to(device),
                                     handle.train_data[client], handle)
            w_locals.append(w)

        w_glob = Aggregation({k: v.clone() for k, v in ori_weight.items()},
                             w_locals, lens, beta, handle.params['eta'],
                             handle.params['defence_method'], handle.params)

        handle.model.load_state_dict(w_glob)
        acc = test.normal_test(epoch, handle.model, handle.test_data, handle.params, handle, poison=False)

        # 贡献度评估部分
        try:
            evaluate_contribution(handle, epoch, agent_name_keys, w_locals, w_glob, ori_weight)
        except Exception as e:
            handle.logger.error(f"贡献度评估失败: {e}")

        # 保存全局模型（每100轮）
        save_global_model(handle, epoch)

        # 记录全局准确度到数据库（可选）
        try:
            from federation_app.models import GlobalAccuracy, FederationTask
            task_obj = FederationTask.objects.get(task_id=handle.task_id)
            GlobalAccuracy.objects.create(
                task=task_obj,
                epoch=epoch,
                accuracy=acc
            )
            handle.logger.info(f"任务 {handle.task_id} 第 {epoch} 轮全局准确度 {acc:.2f}% 已记录到数据库")
        except Exception as e:
            handle.logger.error(f"记录全局准确度失败: {e}")

        handle.logger.info('Epoch {} completed in {:.2f} seconds'.format(epoch, time.time() - start_time))
        time.sleep(15)
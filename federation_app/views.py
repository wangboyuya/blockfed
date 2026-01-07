from .services import task_manager
from .models import FederationTask, TaskLog, TaskParticipant, GlobalAccuracy
import traceback
import logging
from decimal import Decimal

import os
import time
import json
import torch
import logging

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction

logger = logging.getLogger("logger")


def index_redirect(request):
    """根路径重定向"""
    # 如果已登录，跳转到个人中心；否则跳转到登录页
    if request.user.is_authenticated:
        return redirect('profile_page')
    return redirect('login_page')


@login_required(login_url='/login/')
def dashboard(request):
    """主控制面板"""
    tasks_status = task_manager.get_all_tasks_status()

    # 获取任务日志
    recent_logs = TaskLog.objects.select_related('task').order_by('-created_at')[:20]

    context = {
        'tasks_status': tasks_status,
        'recent_logs': recent_logs,
    }
    return render(request, 'federation_app/dashboard.html', context)


@login_required(login_url='/login/')
def prediction_page(request):
    """模型预测页面"""
    return render(request, 'federation_app/predict.html')

# views.py - 修改 create_task 视图
@csrf_exempt
def create_task(request):
    """创建联邦任务"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            task_id = data.get('task_id')
            task_name = data.get('task_name')
            description = data.get('description', '')

            # 新增参数
            model_architecture = data.get('model_architecture', 'r8')
            dataset = data.get('dataset', 'CIFAR10')
            epochs = int(data.get('epochs', 2000))
            reward_pool = float(data.get('reward_pool', 0.00))
            payment_mode = data.get('payment_mode', 'shareholding')
            usage_fee = float(data.get('usage_fee_per_request', 0.50))

            if not task_id or not task_name:
                return JsonResponse({'success': False, 'message': '任务编号和名称不能为空'})

            # 参数验证
            if model_architecture not in ['CNN', 'r8', 'r18', 'r34']:
                return JsonResponse({'success': False, 'message': '不支持的模型结构'})

            if dataset not in ['MNIST', 'CIFAR10']:
                return JsonResponse({'success': False, 'message': '不支持的数据集'})

            if epochs <= 0:
                return JsonResponse({'success': False, 'message': '训练轮数必须大于0'})

            if payment_mode not in ['reward', 'shareholding']:
                return JsonResponse({'success': False, 'message': '无效的支付模式'})

            if payment_mode == 'reward' and reward_pool <= 0:
                return JsonResponse({'success': False, 'message': '奖金池模式下奖金池必须大于0'})

            if usage_fee < 0:
                return JsonResponse({'success': False, 'message': '使用费不能为负数'})

            task_obj = task_manager.create_task(
                task_id=task_id,
                task_name=task_name,
                description=description,
                model_architecture=model_architecture,
                dataset=dataset,
                epochs=epochs,
                reward_pool=reward_pool,
                payment_mode=payment_mode,
                usage_fee_per_request=usage_fee,
                creator=request.user if request.user.is_authenticated else None
            )
            task_manager.start_task(task_id)

            return JsonResponse({
                'success': True,
                'message': f'联邦任务 {task_name} 创建并启动成功',
                'task_id': task_id
            })

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': '仅支持POST请求'})

@csrf_exempt
def join_task(request):
    """加入联邦任务"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            task_id = data.get('task_id')

            if not request.user.is_authenticated:
                return JsonResponse({'success': False, 'message': '请先登录'})

            if not task_id:
                return JsonResponse({'success': False, 'message': '任务编号不能为空'})

            success = task_manager.add_user_to_task(task_id, request.user)

            if success:
                return JsonResponse({
                    'success': True,
                    'message': f'用户 {request.user.username} 成功加入联邦任务 {task_id}'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': f'用户 {request.user.username} 加入联邦任务失败'
                })

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': '仅支持POST请求'})

@csrf_exempt
def leave_task(request):
    """退出联邦任务"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            task_id = data.get('task_id')

            if not request.user.is_authenticated:
                return JsonResponse({'success': False, 'message': '请先登录'})

            if not task_id:
                return JsonResponse({'success': False, 'message': '任务编号不能为空'})

            success = task_manager.remove_user_from_task(task_id, request.user)

            if success:
                return JsonResponse({
                    'success': True,
                    'message': f'用户 {request.user.username} 成功退出联邦任务 {task_id}'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': f'用户 {request.user.username} 退出联邦任务失败'
                })

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': '仅支持POST请求'})

@csrf_exempt
def delete_task(request):
    """删除联邦任务"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            task_id = data.get('task_id')
            
            if not task_id:
                return JsonResponse({'success': False, 'message': '任务编号不能为空'})
            
            # 检查任务是否存在
            try:
                task_obj = FederationTask.objects.get(task_id=task_id)
            except FederationTask.DoesNotExist:
                return JsonResponse({'success': False, 'message': f"任务 {task_id} 不存在"})
            
            # 检查任务是否正在运行
            if task_id in task_manager.tasks:
                task_data = task_manager.tasks[task_id]
                if task_data['thread'] and task_data['thread'].is_alive():
                    return JsonResponse({
                        'success': False, 
                        'message': f'任务 {task_id} 正在运行中，无法删除。请先停止任务。'
                    })
            
            # 删除任务相关的所有数据
            # 1. 从任务管理器中移除（如果存在）
            if task_id in task_manager.tasks:
                del task_manager.tasks[task_id]
            
            # 2. 删除数据库记录（由于外键关联，相关记录也会被删除）
            task_name = task_obj.task_name
            task_obj.delete()
            
            logger.info(f"任务 {task_id} 及相关数据已删除")
            
            return JsonResponse({
                'success': True, 
                'message': f'任务 {task_name} 已成功删除'
            })
                
        except Exception as e:
            logger.error(f"删除任务失败: {e}")
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': '仅支持POST请求'})

@csrf_exempt
def restart_task(request):
    """重新启动任务"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            task_id = data.get('task_id')

            if not task_id:
                return JsonResponse({'success': False, 'message': '任务编号不能为空'})

            # 检查任务是否存在
            try:
                task_obj = FederationTask.objects.get(task_id=task_id)
            except FederationTask.DoesNotExist:
                return JsonResponse({'success': False, 'message': f'任务 {task_id} 不存在'})

            # 权限检查：只有创建者可以重启任务
            if request.user.is_authenticated and task_obj.creator:
                if request.user.id != task_obj.creator.id:
                    return JsonResponse({'success': False, 'message': '只有任务创建者才能重启任务'})

            # 检查任务是否已完成
            if task_obj.status == 'completed':
                return JsonResponse({'success': False, 'message': '已完成的任务无法重启'})

            # 如果任务不在内存中，需要重新创建
            if task_id not in task_manager.tasks:
                # 重新创建任务
                task_manager.create_task(
                    task_id=task_obj.task_id,
                    task_name=task_obj.task_name,
                    description=task_obj.description,
                    model_architecture=task_obj.model_architecture,
                    dataset=task_obj.dataset,
                    epochs=task_obj.epochs,
                    reward_pool=float(task_obj.reward_pool),
                    payment_mode=task_obj.payment_mode,
                    usage_fee_per_request=float(task_obj.usage_fee_per_request),
                    creator=task_obj.creator
                )

            # 启动任务
            task_manager.start_task(task_id)

            return JsonResponse({
                'success': True,
                'message': f'任务 {task_obj.task_name} 已成功重启'
            })

        except Exception as e:
            logger.error(f"重启任务失败: {e}")
            traceback.print_exc()
            return JsonResponse({'success': False, 'message': f'重启任务失败: {str(e)}'})

    return JsonResponse({'success': False, 'message': '仅支持POST请求'})

@csrf_exempt
def clear_logs(request):
    """清空所有日志"""
    if request.method == 'POST':
        try:
            # 删除所有日志记录
            count = TaskLog.objects.all().delete()[0]
            
            logger.info(f"已清空 {count} 条日志记录")
            
            return JsonResponse({
                'success': True, 
                'message': f'已清空 {count} 条日志记录'
            })
                
        except Exception as e:
            logger.error(f"清空日志失败: {e}")
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': '仅支持POST请求'})

def get_task_status(request, task_id):
    """获取任务状态"""
    try:
        status = task_manager.get_task_status(task_id)
        return JsonResponse({'success': True, 'status': status})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

def get_all_status(request):
    """获取所有任务状态"""
    try:
        status_list = task_manager.get_all_tasks_status()
        return JsonResponse({'success': True, 'tasks': status_list})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})
    
@csrf_exempt
def get_accuracy_history(request):
    """获取任务准确度历史"""
    if request.method == 'GET':
        task_id = request.GET.get('task_id')
        
        if not task_id:
            return JsonResponse({'success': False, 'message': '任务编号不能为空'})
        
        try:
            result = task_manager.get_task_accuracy_history(task_id)
            return JsonResponse(result)
        except Exception as e:
            logger.error(f"获取准确度历史API错误: {e}")
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': '仅支持GET请求'})

@csrf_exempt
def get_logs(request):
    """获取系统日志"""
    if request.method == 'GET':
        try:
            # 获取最近的20条日志
            recent_logs = TaskLog.objects.select_related('task').order_by('-created_at')[:20]
            
            logs_data = []
            for log in recent_logs:
                logs_data.append({
                    'task_id': log.task.task_id,
                    'level': log.level,
                    'level_display': log.get_level_display(),
                    'message': log.message,
                    'created_at': log.created_at.isoformat()
                })
            
            return JsonResponse({
                'success': True,
                'logs': logs_data
            })
        except Exception as e:
            logger.error(f"获取系统日志失败: {e}")
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': '仅支持GET请求'})


@csrf_exempt
@login_required
def predict_image(request):
    """图像预测API - 使用ETH支付并自动分红给股东"""
    if request.method == 'POST':
        try:
            # 检查是否有文件上传
            if 'image' not in request.FILES:
                return JsonResponse({'success': False, 'message': '没有上传图像文件'})

            image_file = request.FILES['image']
            task_id = request.POST.get('task_id')
            dataset_type = request.POST.get('dataset_type', 'CIFAR10')
            user = request.user

            if not task_id:
                return JsonResponse({'success': False, 'message': '任务ID不能为空'})

            # 获取任务信息
            try:
                task = FederationTask.objects.get(task_id=task_id)
            except FederationTask.DoesNotExist:
                return JsonResponse({'success': False, 'message': f'任务 {task_id} 不存在'})

            # 检查任务模型状态
            if task.model_status != 'online':
                return JsonResponse({
                    'success': False,
                    'message': f'模型未上线，当前状态: {task.get_model_status_display()}',
                    'model_offline': True
                })

            # 检查用户ETH余额
            usage_fee = float(task.usage_fee_per_request)
            if user.eth_balance < usage_fee:
                return JsonResponse({
                    'success': False,
                    'message': f'ETH余额不足！需要{usage_fee} ETH，当前余额{user.eth_balance:.4f} ETH',
                    'insufficient_eth': True
                })

            # 验证文件类型
            allowed_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']
            file_extension = os.path.splitext(image_file.name)[1].lower()
            if file_extension not in allowed_extensions:
                return JsonResponse({
                    'success': False,
                    'message': f'不支持的文件格式。支持的格式: {", ".join(allowed_extensions)}'
                })

            # 创建临时文件保存上传的图像
            temp_dir = os.path.join(settings.BASE_DIR, 'temp_uploads')
            os.makedirs(temp_dir, exist_ok=True)

            temp_file_path = os.path.join(temp_dir, f'temp_{int(time.time())}{file_extension}')

            with open(temp_file_path, 'wb+') as destination:
                for chunk in image_file.chunks():
                    destination.write(chunk)

            try:
                # 先运行预测（预测失败不扣钱）
                prediction_result = run_model_prediction(temp_file_path, task_id, dataset_type)

                # 预测成功后，调用区块链分红系统
                from .business_logic import ModelUsageService

                # 转换预测结果为字符串
                prediction_str = f"Class: {prediction_result.get('class_name', 'Unknown')} (ID: {prediction_result.get('predicted_class', -1)}), Confidence: {prediction_result.get('confidence', 0):.2f}%"

                # 调用付费和分红逻辑
                payment_result = ModelUsageService.charge_and_distribute(
                    task=task,
                    user=user,
                    prediction_result=prediction_str,
                    input_hash=''
                )

                # 清理临时文件
                os.remove(temp_file_path)

                return JsonResponse({
                    'success': True,
                    'prediction': prediction_result,
                    'payment': {
                        'usage_fee': payment_result['usage_fee'],
                        'user_balance_after': payment_result['user_balance_after'],
                        'tx_hash': payment_result['tx_hash'],
                        'distributions': payment_result['distributions']
                    },
                    'message': f'预测成功！已支付{payment_result["usage_fee"]} ETH，分红已自动发放给{len(payment_result["distributions"])}位股东'
                })

            except ValueError as e:
                # 余额不足或其他业务逻辑错误
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
                return JsonResponse({
                    'success': False,
                    'message': f'支付失败: {str(e)}'
                })
            except Exception as e:
                # 其他错误（预测失败等）
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
                raise e

        except Exception as e:
            logger.error(f"图像预测失败: {e}")
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': '仅支持POST请求'})


def run_model_prediction(image_path, task_id, dataset_type='CIFAR10'):
    """运行模型预测"""
    try:
        # 构建预测脚本路径
        base_dir = settings.BASE_DIR
        core_dir = os.path.join(base_dir, 'federation_core')
        predict_script = os.path.join(core_dir, 'model_predict.py')

        # 检查预测脚本是否存在
        if not os.path.exists(predict_script):
            raise FileNotFoundError(f"模型预测脚本不存在: {predict_script}")

        # 执行预测命令
        import subprocess
        cmd = [
            'python', predict_script,
            '--image', image_path,
            '--task_id', task_id,
            '--dataset_type', dataset_type,
            '--output_format', 'json'
        ]

        logger.info(f"执行预测命令: {' '.join(cmd)}")
        logger.info(f"工作目录: {core_dir}")

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=core_dir)

        logger.info(f"预测命令返回码: {result.returncode}")
        logger.info(f"预测命令标准输出: {result.stdout}")
        logger.info(f"预测命令标准错误: {result.stderr}")

        if result.returncode != 0:
            error_msg = f"预测执行失败: {result.stderr}"
            if result.stdout:
                error_msg += f"\n标准输出: {result.stdout}"
            raise Exception(error_msg)

        # 解析JSON输出
        prediction_result = json.loads(result.stdout)

        return prediction_result

    except Exception as e:
        logger.error(f"运行模型预测时出错: {str(e)}")
        logger.error(f"完整错误信息: {traceback.format_exc()}")
        raise e


@csrf_exempt
def get_available_models(request):
    """获取可用的模型列表"""
    if request.method == 'GET':
        try:
            base_dir = settings.BASE_DIR
            core_dir = os.path.join(base_dir, 'federation_core')
            models_dir = os.path.join(core_dir, 'saved_models')

            available_models = []

            if os.path.exists(models_dir):
                for item in os.listdir(models_dir):
                    item_path = os.path.join(models_dir, item)
                    model_path = os.path.join(item_path, 'global_model.pth')

                    if os.path.isdir(item_path) and os.path.exists(model_path):
                        # 解析任务ID和名称
                        if '_' in item:
                            parts = item.split('_', 1)
                            task_id = parts[0]
                            task_name = parts[1] if len(parts) > 1 else task_id
                        else:
                            task_id = item
                            task_name = item

                        # 获取模型信息
                        try:
                            checkpoint = torch.load(model_path, map_location='cpu')
                            epoch = checkpoint.get('epoch', '未知')

                            available_models.append({
                                'task_id': task_id,
                                'task_name': task_name,
                                'epoch': epoch,
                                'path': item_path
                            })
                        except Exception as e:
                            logger.warning(f"无法读取模型信息 {item_path}: {e}")
                            continue

            return JsonResponse({
                'success': True,
                'models': available_models
            })

        except Exception as e:
            logger.error(f"获取可用模型列表失败: {e}")
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': '仅支持GET请求'})


@csrf_exempt
def get_model_info(request, task_id):
    """获取特定模型的详细信息"""
    if request.method == 'GET':
        try:
            base_dir = settings.BASE_DIR
            core_dir = os.path.join(base_dir, 'federation_core')
            models_dir = os.path.join(core_dir, 'saved_models')

            # 查找匹配的模型目录
            model_dir = None
            for item in os.listdir(models_dir):
                if item.startswith(task_id):
                    model_dir = os.path.join(models_dir, item)
                    break

            if not model_dir or not os.path.exists(model_dir):
                return JsonResponse({'success': False, 'message': f'未找到任务 {task_id} 的模型'})

            model_path = os.path.join(model_dir, 'global_model.pth')

            if not os.path.exists(model_path):
                return JsonResponse({'success': False, 'message': '模型文件不存在'})

            # 读取模型信息
            checkpoint = torch.load(model_path, map_location='cpu')

            model_info = {
                'task_id': task_id,
                'task_name': checkpoint.get('task_name', '未知'),
                'epoch': checkpoint.get('epoch', '未知'),
                'model_size': f"{os.path.getsize(model_path) / 1024 / 1024:.2f} MB",
                'last_modified': time.ctime(os.path.getmtime(model_path))
            }

            return JsonResponse({
                'success': True,
                'model_info': model_info
            })

        except Exception as e:
            logger.error(f"获取模型信息失败: {e}")
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': '仅支持GET请求'})


def login_page(request):
    """登录页面"""
    # 如果已登录，重定向到个人中心
    if request.user.is_authenticated:
        return redirect('profile_page')
    return render(request, 'federation_app/login.html')


@login_required(login_url='/login/')
def profile_page(request):
    """个人中心页面"""
    return render(request, 'federation_app/profile.html')

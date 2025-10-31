# model_predict.py
import argparse
import os
import sys
import torch
import traceback
from PIL import Image, ImageOps
import torchvision.transforms as transforms
import json

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from models.ResNet8 import ResNet8
    from device import device
except ImportError as e:
    print(f"导入模块失败: {e}", file=sys.stderr)
    sys.exit(1)

# CIFAR-10 类别标签
CIFAR10_CLASSES = [
    'airplane', 'automobile', 'bird', 'cat', 'deer',
    'dog', 'frog', 'horse', 'ship', 'truck'
]


def log_debug(message):
    """调试日志输出到标准错误"""
    print(f"DEBUG: {message}", file=sys.stderr)


def load_model(task_id, model_dir=None):
    """加载指定任务的模型"""
    try:
        if model_dir is None:
            # 默认模型目录
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            core_dir = os.path.join(base_dir, 'federation_core')
            model_dir = os.path.join(core_dir, 'saved_models')

        log_debug(f"查找模型目录: {model_dir}")
        log_debug(f"任务ID: {task_id}")

        # 查找任务目录
        task_dirs = [d for d in os.listdir(model_dir) if d.startswith(str(task_id))]

        if not task_dirs:
            raise FileNotFoundError(f"未找到任务 {task_id} 的模型目录")

        # 使用第一个匹配的目录
        task_dir = os.path.join(model_dir, task_dirs[0])
        model_path = os.path.join(task_dir, "global_model.pth")

        log_debug(f"模型路径: {model_path}")
        log_debug(f"模型文件存在: {os.path.exists(model_path)}")

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"在目录 {task_dir} 中未找到模型文件 global_model.pth")

        # 加载模型检查点
        log_debug("正在加载模型检查点...")
        checkpoint = torch.load(model_path, map_location=device)
        log_debug("模型检查点加载成功")
        log_debug(f"检查点类型: {type(checkpoint)}")

        # 创建模型实例
        log_debug("创建模型实例...")
        model = ResNet8(num_classes=10)  # 默认10个类别

        # 处理不同的模型文件格式
        if isinstance(checkpoint, dict):
            if 'model_state_dict' in checkpoint:
                # 格式1: 包含元数据的检查点
                model.load_state_dict(checkpoint['model_state_dict'])
                log_debug("使用 model_state_dict 加载模型")
                epoch = checkpoint.get('epoch', '未知')
                log_debug(f"训练轮次: {epoch}")
            elif 'state_dict' in checkpoint:
                # 格式2: 包含state_dict的检查点
                model.load_state_dict(checkpoint['state_dict'])
                log_debug("使用 state_dict 加载模型")
            else:
                # 格式3: 检查点本身就是状态字典
                try:
                    model.load_state_dict(checkpoint)
                    log_debug("直接使用检查点字典作为状态字典加载模型")
                except Exception as e:
                    log_debug(f"无法将检查点作为状态字典加载: {e}")
                    raise KeyError("无法识别模型检查点格式")
        else:
            # 格式4: 检查点直接是状态字典（OrderedDict）
            try:
                model.load_state_dict(checkpoint)
                log_debug("直接使用检查点作为状态字典加载模型")
            except Exception as e:
                log_debug(f"无法加载状态字典: {e}")
                raise

        model.to(device)
        model.eval()

        log_debug(f"成功加载任务 {task_id} 的模型")
        return model

    except Exception as e:
        log_debug(f"加载模型失败: {str(e)}")
        log_debug(f"错误详情: {traceback.format_exc()}")
        raise


def preprocess_image(image_path, dataset_type='CIFAR10'):
    """预处理图像，适配模型输入要求"""
    try:
        log_debug(f"预处理图像: {image_path}")
        log_debug(f"数据集类型: {dataset_type}")

        # 读取图像
        image = Image.open(image_path).convert('RGB')
        log_debug(f"原始图像尺寸: {image.size}")
        log_debug(f"原始图像模式: {image.mode}")

        if dataset_type == 'CIFAR10':
            # CIFAR-10 预处理：32x32，标准化
            transform = transforms.Compose([
                transforms.Resize((32, 32)),  # 调整大小到32x32
                transforms.CenterCrop((32, 32)),  # 中心裁剪确保32x32
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
            ])
        elif dataset_type == 'MNIST':
            # MNIST 预处理：28x28，灰度，标准化
            transform = transforms.Compose([
                transforms.Resize((28, 28)),
                transforms.CenterCrop((28, 28)),
                transforms.Grayscale(num_output_channels=1),  # 转换为单通道
                transforms.ToTensor(),
                transforms.Normalize((0.1307,), (0.3081,))
            ])
        else:
            raise ValueError(f"不支持的dataset_type: {dataset_type}")

        # 应用变换并添加batch维度
        image_tensor = transform(image).unsqueeze(0).to(device)
        log_debug(f"预处理后张量形状: {image_tensor.shape}")

        return image_tensor

    except Exception as e:
        log_debug(f"图像预处理失败: {str(e)}")
        log_debug(f"错误详情: {traceback.format_exc()}")
        raise


def predict_image(model, image_tensor, dataset_type='CIFAR10'):
    """使用模型进行预测"""
    try:
        log_debug("开始模型预测...")
        with torch.no_grad():
            outputs = model(image_tensor)
            log_debug(f"模型输出形状: {outputs.shape}")

            probabilities = torch.nn.functional.softmax(outputs, dim=1)
            confidence, predicted = torch.max(probabilities, 1)

            confidence_score = confidence.item()
            predicted_class = predicted.item()

            if dataset_type == 'CIFAR10':
                class_name = CIFAR10_CLASSES[predicted_class]
            else:
                class_name = str(predicted_class)

            # 获取所有类别的概率
            all_probabilities = {i: prob.item() for i, prob in enumerate(probabilities[0])}

            log_debug(f"预测结果: 类别 {predicted_class} ({class_name}), 置信度: {confidence_score:.4f}")

            return {
                'predicted_class': predicted_class,
                'class_name': class_name,
                'confidence': confidence_score,
                'all_probabilities': all_probabilities
            }

    except Exception as e:
        log_debug(f"模型预测失败: {str(e)}")
        log_debug(f"错误详情: {traceback.format_exc()}")
        raise


def main():
    parser = argparse.ArgumentParser(description='联邦学习模型预测')
    parser.add_argument('--image', type=str, required=True, help='输入图像路径')
    parser.add_argument('--task_id', type=str, required=True, help='任务ID')
    parser.add_argument('--dataset_type', type=str, default='CIFAR10',
                        choices=['CIFAR10', 'MNIST'], help='数据集类型')
    parser.add_argument('--model_dir', type=str, help='模型目录路径（可选）')
    parser.add_argument('--output_format', type=str, default='json',
                        choices=['json', 'text'], help='输出格式')

    args = parser.parse_args()

    try:
        log_debug("=== 开始模型预测 ===")

        # 加载模型
        log_debug(f"正在加载任务 {args.task_id} 的模型...")
        model = load_model(args.task_id, args.model_dir)

        # 预处理图像
        log_debug(f"预处理图像: {args.image}")
        image_tensor = preprocess_image(args.image, args.dataset_type)

        # 进行预测
        log_debug("正在进行预测...")
        result = predict_image(model, image_tensor, args.dataset_type)

        # 输出结果 - 只输出到标准输出，确保是有效的JSON
        if args.output_format == 'json':
            print(json.dumps(result, ensure_ascii=False))
        else:
            # 文本格式也输出到标准输出，但确保格式干净
            output_lines = [
                f"预测结果:",
                f"  类别: {result['class_name']} (ID: {result['predicted_class']})",
                f"  置信度: {result['confidence']:.4f}",
                f"  所有类别概率:"
            ]
            for class_id, prob in result['all_probabilities'].items():
                class_name = CIFAR10_CLASSES[class_id] if args.dataset_type == 'CIFAR10' else str(class_id)
                output_lines.append(f"    {class_name}: {prob:.4f}")

            print("\n".join(output_lines))

        log_debug("=== 预测完成 ===")

    except Exception as e:
        # 错误信息输出到标准错误
        error_msg = f"预测过程失败: {str(e)}"
        print(error_msg, file=sys.stderr)
        log_debug(f"完整错误信息: {traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
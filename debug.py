# debug_prediction.py
import os
import subprocess
import json


def debug_prediction():
    """调试预测脚本的输出"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    core_dir = os.path.join(base_dir, 'BlockFedNew\\federation_core')
    predict_script = os.path.join(core_dir, 'model_predict.py')

    # 创建测试图像
    from PIL import Image
    import numpy as np
    test_image_path = os.path.join(base_dir, 'debug_test.jpg')
    test_image_array = np.random.randint(0, 255, (32, 32, 3), dtype=np.uint8)
    test_image = Image.fromarray(test_image_array)
    test_image.save(test_image_path)

    # 查找可用的任务ID
    models_dir = os.path.join(core_dir, 'saved_models')
    task_id = None
    if os.path.exists(models_dir):
        for item in os.listdir(models_dir):
            if os.path.isdir(os.path.join(models_dir, item)):
                task_id = item.split('_')[0]
                break

    if not task_id:
        print("❌ 没有找到可用的任务ID")
        return

    print(f"使用任务ID: {task_id}")

    # 执行预测命令
    cmd = [
        'python', predict_script,
        '--image', test_image_path,
        '--task_id', task_id,
        '--dataset_type', 'CIFAR10',
        '--output_format', 'json'
    ]

    print(f"执行命令: {' '.join(cmd)}")
    print(f"工作目录: {core_dir}")

    # 修改：先捕获字节流，然后尝试解码
    result = subprocess.run(cmd, capture_output=True, cwd=core_dir)

    # 解码标准输出和标准错误
    try:
        stdout = result.stdout.decode('utf-8')
    except UnicodeDecodeError:
        try:
            stdout = result.stdout.decode('gbk')
        except UnicodeDecodeError:
            stdout = result.stdout.decode('gbk', errors='ignore')

    try:
        stderr = result.stderr.decode('utf-8')
    except UnicodeDecodeError:
        try:
            stderr = result.stderr.decode('gbk')
        except UnicodeDecodeError:
            stderr = result.stderr.decode('gbk', errors='ignore')

    print(f"\n返回码: {result.returncode}")
    print(f"\n标准输出长度: {len(stdout)}")
    print(f"标准输出内容: {repr(stdout)}")
    print(f"\n标准错误长度: {len(stderr)}")
    print(f"标准错误内容: {repr(stderr)}")

    # 尝试解析JSON
    if result.returncode == 0 and stdout.strip():
        try:
            parsed = json.loads(stdout)
            print(f"\n✅ JSON解析成功: {parsed}")
        except json.JSONDecodeError as e:
            print(f"\n❌ JSON解析失败: {e}")
            print(f"原始输出: {stdout}")

    # 清理
    if os.path.exists(test_image_path):
        os.remove(test_image_path)


if __name__ == "__main__":
    debug_prediction()
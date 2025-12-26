# federation_app/blockchain_utils.py
from web3 import Web3
import json
import os
from django.conf import settings

# 连接到 Ganache (确保 Ganache 已启动)
w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:7545'))

def get_contract(contract_name):
    # 根据你的目录结构定位 Truffle 编译后的 JSON
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(base_path, 'blockchain/build/contracts', f'{contract_name}.json')
    
    with open(json_path, 'r') as f:
        contract_data = json.load(f)
    
    # 自动获取当前网络 ID (Ganache 通常是 5777)
    network_id = list(contract_data['networks'].keys())[0]
    contract_address = contract_data['networks'][network_id]['address']
    abi = contract_data['abi']
    
    return w3.eth.contract(address=contract_address, abi=abi)

def sync_contribution_to_chain(task_id, contribution_data, model_hash):
    """将贡献度比例上链"""
    try:
        manager_contract = get_contract('FederationManager')
        # 使用 Ganache 的第一个账号作为管理员执行交易
        admin_account = w3.eth.accounts[0]
        
        # 准备数据：地址列表和放大后的比例（Solidity 不支持浮点数，需转为整数）
        addresses = []
        ratios = []
        for user_id, contribution in contribution_data.items():
            # 这里建议在 User 模型中增加一个 wallet_address 字段，
            # 暂时用映射或测试地址代替
            from .models import User
            user = User.objects.get(id=user_id)
            # 假设你给用户分配了 Ganache 的地址，或者先模拟一个
            test_address = w3.eth.accounts[int(user_id) % 10] 
            addresses.append(test_address)
            ratios.append(int(float(contribution) * 10000)) # 放大一万倍

        tx_hash = manager_contract.functions.setContributionRatios(
            task_id, addresses, ratios, model_hash
        ).transact({'from': admin_account})
        
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt.status == 1
    except Exception as e:
        print(f"区块链同步失败: {e}")
        return False
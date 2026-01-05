"""
用户认证相关视图
"""
import json
from decimal import Decimal
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction
from .models import User, Transaction
from .datablock_service import datablock_market_service
from .blockchain_utils import sync_contribution_to_chain, get_contract, w3

@csrf_exempt
@require_http_methods(["POST"])
@transaction.atomic
def register_user(request):
    """用户注册 - 自动分配Ganache账户和3个免费数据块"""
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        email = data.get('email', '')

        if not username or not password:
            return JsonResponse({'success': False, 'error': '用户名和密码不能为空'})

        if User.objects.filter(username=username).exists():
            return JsonResponse({'success': False, 'error': '用户名已存在'})

        # 自动分配Ganache账户索引（0-9）
        assigned_indices = set(User.objects.filter(ganache_index__isnull=False).values_list('ganache_index', flat=True))
        available_indices = set(range(10)) - assigned_indices

        if not available_indices:
            return JsonResponse({'success': False, 'error': 'Ganache账户已满（最多10个用户），请联系管理员'})

        ganache_index = min(available_indices)  # 分配最小的可用索引

        # 创建用户（绑定Ganache账户）
        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
            ganache_index=ganache_index,
            balance=Decimal('0.00'),  # 保留字段但不使用
            virtual_coins=0  # 虚拟币初始为0，需用ETH购买
        )

        # 登录用户
        login(request, user)

        return JsonResponse({
            'success': True,
            'message': f'注册成功，已分配Ganache账户{ganache_index}',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'ganache_index': user.ganache_index,
                'wallet_address': user.wallet_address,
                'eth_balance': user.eth_balance,
                'virtual_coins': user.virtual_coins
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def login_user(request):
    """用户登录"""
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return JsonResponse({'success': False, 'error': '用户名和密码不能为空'})

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return JsonResponse({
                'success': True,
                'message': '登录成功',
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'ganache_index': user.ganache_index,
                    'wallet_address': user.wallet_address,
                    'eth_balance': user.eth_balance
                }
            })
        else:
            return JsonResponse({'success': False, 'error': '用户名或密码错误'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def logout_user(request):
    """用户登出"""
    try:
        logout(request)
        return JsonResponse({'success': True, 'message': '登出成功'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def get_user_profile(request):
    """获取用户信息"""
    try:
        user = request.user
        return JsonResponse({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'ganache_index': user.ganache_index,
                'wallet_address': user.wallet_address,
                'eth_balance': user.eth_balance,
                'date_joined': user.date_joined.strftime('%Y-%m-%d %H:%M:%S')
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def get_user_transactions(request):
    """获取用户交易记录"""
    try:
        user = request.user
        transactions = Transaction.objects.filter(user=user).order_by('-created_at')[:50]

        transactions_data = [{
            'id': t.id,
            'type': t.transaction_type,
            'type_display': t.get_transaction_type_display(),
            'amount': float(t.amount),
            'balance_before': float(t.balance_before),
            'balance_after': float(t.balance_after),
            'description': t.description,
            'created_at': t.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'related_task_id': t.related_task.task_id if t.related_task else None
        } for t in transactions]

        return JsonResponse({
            'success': True,
            'transactions': transactions_data
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
@transaction.atomic
def recharge_balance(request):
    """充值余额 - 从管理员账户转ETH到用户Ganache账户"""
    try:
        data = json.loads(request.body)
        amount = Decimal(str(data.get('amount', 0)))

        if amount <= 0:
            return JsonResponse({'success': False, 'error': '充值金额必须大于0'})

        user = request.user

        if user.ganache_index is None:
            return JsonResponse({'success': False, 'error': '用户未绑定Ganache账户，请联系管理员'})

        # 获取充值前后的ETH余额
        balance_before = user.eth_balance

        # 从管理员账户(accounts[0])转账ETH到用户账户
        admin_address = w3.eth.accounts[0]
        user_address = user.wallet_address
        amount_wei = w3.to_wei(amount, 'ether')

        # 执行ETH转账
        tx_hash = w3.eth.send_transaction({
            'from': admin_address,
            'to': user_address,
            'value': amount_wei,
            'gas': 21000
        })

        # 等待交易确认
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status != 1:
            return JsonResponse({'success': False, 'error': '区块链交易失败'})

        balance_after = user.eth_balance

        # 记录交易（金额单位为ETH）
        Transaction.objects.create(
            user=user,
            transaction_type='recharge',
            amount=amount,
            balance_before=Decimal(str(balance_before)),
            balance_after=Decimal(str(balance_after)),
            description=f'充值{amount} ETH，交易哈希: {receipt.transactionHash.hex()[:10]}...'
        )

        return JsonResponse({
            'success': True,
            'message': f'充值成功，已转入{amount} ETH',
            'eth_balance': user.eth_balance,
            'tx_hash': receipt.transactionHash.hex()
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'充值失败: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
@transaction.atomic
def purchase_virtual_coins(request):
    """使用ETH购买虚拟币"""
    try:
        data = json.loads(request.body)
        coin_amount = int(data.get('amount', 0))

        if coin_amount <= 0:
            return JsonResponse({'success': False, 'error': '购买数量必须大于0'})

        # 汇率：1 ETH = 1000 虚拟币
        exchange_rate = 1000
        eth_cost = Decimal(str(coin_amount / exchange_rate))

        user = request.user

        if not user.wallet_address:
            return JsonResponse({'success': False, 'error': '用户未绑定Ganache账户'})

        if user.eth_balance < float(eth_cost):
            return JsonResponse({
                'success': False,
                'error': f'ETH余额不足，需要{eth_cost:.4f} ETH，当前余额{user.eth_balance:.4f} ETH'
            })

        # 获取购买前余额
        eth_balance_before = user.eth_balance

        # 从用户账户转ETH到管理员账户（系统金库）
        admin_address = w3.eth.accounts[0]
        amount_wei = w3.to_wei(eth_cost, 'ether')

        tx_hash = w3.eth.send_transaction({
            'from': user.wallet_address,
            'to': admin_address,
            'value': amount_wei,
            'gas': 21000
        })

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status != 1:
            return JsonResponse({'success': False, 'error': '区块链交易失败'})

        eth_balance_after = user.eth_balance

        # 增加虚拟币
        user.virtual_coins += coin_amount
        user.save()

        # 记录交易
        Transaction.objects.create(
            user=user,
            transaction_type='purchase',
            amount=eth_cost,
            balance_before=Decimal(str(eth_balance_before)),
            balance_after=Decimal(str(eth_balance_after)),
            description=f'用{eth_cost:.4f} ETH购买{coin_amount}虚拟币，交易哈希: {receipt.transactionHash.hex()[:10]}...'
        )

        return JsonResponse({
            'success': True,
            'message': f'成功购买{coin_amount}虚拟币',
            'eth_balance': user.eth_balance,
            'virtual_coins': user.virtual_coins,
            'tx_hash': receipt.transactionHash.hex()
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'购买失败: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
@transaction.atomic
def purchase_data_blocks(request):
    """使用虚拟币购买数据块"""
    try:
        data = json.loads(request.body)
        data_block_ids = data.get('data_block_ids', [])
        cost_per_block = 10

        if not data_block_ids:
            return JsonResponse({'success': False, 'error': '请选择要购买的数据块'})

        user = request.user
        total_cost = len(data_block_ids) * cost_per_block

        if user.virtual_coins < total_cost:
            return JsonResponse({
                'success': False,
                'error': f'虚拟币不足，需要{total_cost}虚拟币，当前仅有{user.virtual_coins}虚拟币'
            })

        user.virtual_coins -= total_cost
        user.save()

        return JsonResponse({
            'success': True,
            'message': f'成功购买{len(data_block_ids)}个数据块',
            'virtual_coins': user.virtual_coins,
            'purchased_blocks': data_block_ids
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
def check_auth_status(request):
    """检查用户登录状态"""
    if request.user.is_authenticated:
        return JsonResponse({
            'authenticated': True,
            'user': {
                'id': request.user.id,
                'username': request.user.username,
                'ganache_index': request.user.ganache_index,
                'wallet_address': request.user.wallet_address,
                'eth_balance': request.user.eth_balance
            }
        })
    else:
        return JsonResponse({'authenticated': False})

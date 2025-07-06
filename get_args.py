import argparse

def parse_mixed_value(value):
    """根据值的内容解析为不同的类型（浮点型、字符串和None）"""
    if value.lower() == 'none':  # 如果是 'None' 或 'none'，将其转换为 None
        return None
    try:
        # 尝试转换为浮点数
        return float(value)
    except ValueError:
        # 如果无法转换为浮点数，返回原始字符串
        return value

def get_args():
    parser = argparse.ArgumentParser(description="")
    
    # 账户创建相关参数
    parser.add_argument("--usr_name", type=str, default="demo", help="usr_name")
    parser.add_argument("--init_fund",type=float,default=1000000,help="init_funds")
    parser.add_argument("--margin_call",type=float,default=100000.00)
    
    # 开仓相关参数
    parser.add_argument("--code",type=str,required=True,help="contract code")

    parser.add_argument("--target",type=str,default='open')
    parser.add_argument("--source",type=str)
    parser.add_argument("--start_time",type=str,)
    parser.add_argument("--end_time",type=str,)
    parser.add_argument("--open",type=str,default='open')
    parser.add_argument("--high",type=str,default='high')
    parser.add_argument("--low",type=str,default='low')
    parser.add_argument("--settle",type=str,default='settle')
    
    parser.add_argument("--shares",type=int,default=1)

    parser.add_argument('--stop_loss', type=parse_mixed_value, nargs='+',)

    # 交易策略指定
    parser.add_argument('--input_mode',type=str,default='in')
    parser.add_argument('--trade_strategy',type=str,)
    parser.add_argument('--lag',type=int,default=5)
    parser.add_argument('--short',type=int,default=5)
    parser.add_argument('--long',type=int,default=20)
    parser.add_argument('--threshold',type=float,default=1.0)

    parser.add_argument('--ubr',type=float,default=0.75)
    parser.add_argument('--lbr',type=float,default=0.25)
    parser.add_argument('--level',type=float,default=4500.00)
    
    # 交易日志
    parser.add_argument("--log_dir",type=str,)
    args = parser.parse_args()

    args.config = {k: v for k,v in vars(args).items() if k in {"source","lag","short","long","threshold","ubr","lbr","level"}}
    args.query_config = {k: v for k,v in vars(args).items() if k in {"target","settle","open","high","low"}}
    return args

args = get_args()

    

   

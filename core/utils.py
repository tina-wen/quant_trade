from datetime import datetime
from get_args import args

def get_log_name():
    return 'share' + str(args.shares) + '_' + datetime.now().strftime("%Y%m%d%H%M%S") +'.log'

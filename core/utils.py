from datetime import datetime

def get_log_name(share):
    return 'share' + str(share) + '_' + datetime.now().strftime("%Y%m%d%H%M%S") +'.log'

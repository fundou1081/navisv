# navisv 配置文件
import os

# ==================== 工具路径配置 ====================

# slang 二进制文件路径
# 环境变量: NAVISV_SLANG_BIN
SLANG_BIN = os.environ.get(
    'NAVISV_SLANG_BIN',
    os.path.expanduser('~/my_dv_proj/slang/slang')
)

# slang-netlist 二进制文件路径
# 环境变量: NAVISV_NETLIST_BIN
NETLIST_BIN = os.environ.get(
    'NAVISV_NETLIST_BIN',
    os.path.expanduser('~/my_dv_proj/slang-netlist/build/tools/driver/slang-netlist')
)

# ==================== 缓存配置 ====================

# AST/Netlist JSON 缓存目录
# 环境变量: NAVISV_CACHE_DIR
CACHE_DIR = os.environ.get(
    'NAVISV_CACHE_DIR',
    os.path.expanduser('~/.cache/navisv')
)

# ==================== 构建配置 ====================

# slang 构建参数
SLANG_BUILD_ARGS = os.environ.get('NAVISV_SLANG_BUILD_ARGS', '-j4')

# ==================== 工具函数 ====================

def get_slang_bin():
    """获取 slang 二进制路径"""
    return os.path.expanduser(SLANG_BIN)

def get_netlist_bin():
    """获取 slang-netlist 二进制路径"""
    return os.path.expanduser(NETLIST_BIN)

def ensure_cache_dir():
    """确保缓存目录存在"""
    cache = os.path.expanduser(CACHE_DIR)
    os.makedirs(cache, exist_ok=True)
    return cache

def check_tools():
    """检查依赖工具是否可用"""
    from pathlib import Path
    
    slang = Path(get_slang_bin())
    netlist = Path(get_netlist_bin())
    
    errors = []
    
    if not slang.exists():
        errors.append(f"slang not found: {slang}")
    elif not os.access(slang, os.X_OK):
        errors.append(f"slang not executable: {slang}")
    
    if not netlist.exists():
        errors.append(f"slang-netlist not found: {netlist}")
    elif not os.access(netlist, os.X_OK):
        errors.append(f"slang-netlist not executable: {netlist}")
    
    return errors if errors else None
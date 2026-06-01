#!/usr/bin/env bash
#
# install_dependencies.sh
# 一键编译并安装 navisv 的两个核心依赖：slang + slang-netlist
#
# 用法:
#   ./scripts/install_dependencies.sh                # 默认 (Release + 最大并行)
#   ./scripts/install_dependencies.sh --debug        # Debug 构建
#   ./scripts/install_dependencies.sh --clean        # 清理后重新构建
#   ./scripts/install_dependencies.sh --skip-slang   # 跳过 slang (已编译)
#   ./scripts/install_dependencies.sh --skip-netlist # 跳过 slang-netlist
#   ./scripts/install_dependencies.sh --prefix DIR   # 安装到指定目录
#   ./scripts/install_dependencies.sh --help         # 显示帮助
#
# 编译完成后,会自动设置环境变量并打印 export 命令。
# 建议把下面两行加到 ~/.zshrc 或 ~/.bashrc:
#   export NAVISV_SLANG_BIN=/path/to/slang
#   export NAVISV_NETLIST_BIN=/path/to/slang-netlist
#

set -e  # 遇错退出
set -u  # 未定义变量报错

# ── 颜色输出 (非 tty 时自动关闭) ─────────────────────────────────────
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    NC='\033[0m'  # 无色
else
    RED='' GREEN='' YELLOW='' BLUE='' CYAN='' NC=''
fi

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()     { echo -e "${RED}[ERROR]${NC} $*" >&2; }
section() { echo -e "\n${CYAN}═══════════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $*${NC}"; echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"; }

# ── 平台检测 ───────────────────────────────────────────────────────────
detect_platform() {
    local uname_s uname_m
    uname_s=$(uname -s 2>/dev/null || echo "Unknown")
    uname_m=$(uname -m 2>/dev/null || echo "Unknown")

    PLATFORM_OS="unknown"
    PLATFORM_ENV="native"     # native / msys2 / cygwin / wsl
    PLATFORM_PKG_MGR=""        # brew / apt / dnf / pacman / choco / scoop
    PLATFORM_INSTALL_CMD=""    # 安装 build 工具的提示命令
    EXE_EXT=""                 # .exe on Windows

    case "$uname_s" in
        Darwin)
            PLATFORM_OS="macos"
            PLATFORM_PKG_MGR="brew"
            PLATFORM_INSTALL_CMD="xcode-select --install && brew install cmake git"
            ;;
        Linux)
            PLATFORM_OS="linux"
            # 检测 WSL
            if [[ -f /proc/version ]] && grep -qiE "microsoft|wsl" /proc/version 2>/dev/null; then
                PLATFORM_ENV="wsl"
            fi
            # 检测发行版
            if command -v apt &>/dev/null; then
                PLATFORM_PKG_MGR="apt"
                PLATFORM_INSTALL_CMD="sudo apt update && sudo apt install -y cmake g++ git build-essential"
            elif command -v dnf &>/dev/null; then
                PLATFORM_PKG_MGR="dnf"
                PLATFORM_INSTALL_CMD="sudo dnf install -y cmake gcc-c++ git make"
            elif command -v yum &>/dev/null; then
                PLATFORM_PKG_MGR="yum"
                PLATFORM_INSTALL_CMD="sudo yum install -y cmake gcc-c++ git make"
            elif command -v pacman &>/dev/null; then
                PLATFORM_PKG_MGR="pacman"
                PLATFORM_INSTALL_CMD="sudo pacman -S --needed cmake gcc git make"
            elif command -v apk &>/dev/null; then
                PLATFORM_PKG_MGR="apk"
                PLATFORM_INSTALL_CMD="sudo apk add cmake g++ git make musl-dev"
            elif command -v zypper &>/dev/null; then
                PLATFORM_PKG_MGR="zypper"
                PLATFORM_INSTALL_CMD="sudo zypper install -y cmake gcc-c++ git make"
            fi
            ;;
        MINGW*|MSYS*|CYGWIN*)
            PLATFORM_OS="windows"
            EXE_EXT=".exe"
            if [[ "$uname_s" == CYGWIN* ]]; then
                PLATFORM_ENV="cygwin"
            else
                PLATFORM_ENV="msys2"
            fi
            # Windows 上包管理器
            if command -v choco &>/dev/null; then
                PLATFORM_PKG_MGR="choco"
                PLATFORM_INSTALL_CMD="choco install -y cmake git mingw make"
            elif command -v scoop &>/dev/null; then
                PLATFORM_PKG_MGR="scoop"
                PLATFORM_INSTALL_CMD="scoop install cmake git make"
            elif command -v winget &>/dev/null; then
                PLATFORM_PKG_MGR="winget"
                PLATFORM_INSTALL_CMD="winget install Kitware.CMake Git.MinGit"
            else
                PLATFORM_INSTALL_CMD="请安装 cmake, git, make (推荐: choco install cmake git mingw make)"
            fi
            ;;
        *)
            # Windows 备用检测 (如果 uname 不存在)
            if [[ -n "${OS:-}" ]] && [[ "$OS" == "Windows_NT" ]]; then
                PLATFORM_OS="windows"
                EXE_EXT=".exe"
            fi
            ;;
    esac

    # 架构
    PLATFORM_ARCH="$uname_m"
    case "$uname_m" in
        x86_64|amd64)  PLATFORM_ARCH="x86_64" ;;
        aarch64|arm64) PLATFORM_ARCH="arm64" ;;
        i386|i686)     PLATFORM_ARCH="x86" ;;
    esac

    # 友好的平台描述
    case "$PLATFORM_OS" in
        macos)   PLATFORM_DESC="macOS ($PLATFORM_ARCH)" ;;
        linux)   PLATFORM_DESC="Linux ($PLATFORM_ARCH)$([[ "$PLATFORM_ENV" == "wsl" ]] && echo ' / WSL')" ;;
        windows) PLATFORM_DESC="Windows ($PLATFORM_ARCH / $PLATFORM_ENV)" ;;
        *)       PLATFORM_DESC="未知平台 ($uname_s $uname_m)" ;;
    esac
}

# ── 检测 CPU 核心数 (跨平台) ──────────────────────────────────────────
detect_cpu_count() {
    local n=""
    # 1. 尝试 nproc (Linux/Cygwin/MSYS2)
    if command -v nproc &>/dev/null; then
        n=$(nproc 2>/dev/null)
    fi
    # 2. macOS
    if [[ -z "$n" ]] && command -v sysctl &>/dev/null; then
        n=$(sysctl -n hw.ncpu 2>/dev/null)
    fi
    # 3. Windows 原生 (cmd)
    if [[ -z "$n" ]] && command -v wmic &>/dev/null; then
        n=$(wmic cpu get NumberOfLogicalProcessors 2>/dev/null | awk 'NR==2{print $1}')
    fi
    # 4. Windows PowerShell
    if [[ -z "$n" ]] && command -v powershell &>/dev/null; then
        n=$(powershell -Command "[Environment]::ProcessorCount" 2>/dev/null | tr -d '\r')
    fi
    # 5. fallback: /proc/cpuinfo (Linux)
    if [[ -z "$n" ]] && [[ -r /proc/cpuinfo ]]; then
        n=$(grep -c ^processor /proc/cpuinfo 2>/dev/null)
    fi
    # 6. fallback: 环境变量
    if [[ -z "$n" ]] && [[ -n "${NUMBER_OF_PROCESSORS:-}" ]]; then
        n="$NUMBER_OF_PROCESSORS"
    fi
    # 7. 硬编码 fallback
    [[ -z "$n" ]] && n=4

    echo "$n"
}

# ── 设置脚本生成器 (跨平台) ──────────────────────────────────────────
setup_script_path() {
    # 根据 shell 决定 .rc 文件
    if [[ "$PLATFORM_OS" == "windows" ]]; then
        SHELL_RC="$HOME/.bashrc"  # Git Bash 默认
        if [[ -n "${BASH_ENV:-}" ]]; then
            SHELL_RC="$BASH_ENV"
        fi
    elif [[ -n "${ZSH_VERSION:-}" ]] || [[ "$SHELL" == *"zsh"* ]]; then
        SHELL_RC="$HOME/.zshrc"
    else
        SHELL_RC="$HOME/.bashrc"
    fi
}

# ── 默认参数 ───────────────────────────────────────────────────────────
BUILD_TYPE="Release"
CLEAN_BUILD=0
SKIP_SLANG=0
SKIP_NETLIST=0
PREFIX_DIR=""
SLANG_DIR="$HOME/my_dv_proj/slang"
NETLIST_DIR="$HOME/my_dv_proj/slang-netlist"
JOBS=4  # 后面会在 detect_platform 后覆盖

# ── 帮助信息 ───────────────────────────────────────────────────────────
usage() {
    cat <<EOF
navisv 依赖安装脚本 (跨平台: macOS / Linux / Windows)

用法:
    $0 [选项]

选项:
    --debug               Debug 构建 (默认 Release)
    --clean               清理 build 目录后重新构建
    --skip-slang          跳过 slang 编译
    --skip-netlist        跳过 slang-netlist 编译
    --prefix DIR          自定义安装目录
    --slang-dir DIR       slang 源码目录 (默认 ~/my_dv_proj/slang)
    --netlist-dir DIR     slang-netlist 源码目录 (默认 ~/my_dv_proj/slang-netlist)
    --jobs N              并行编译数 (默认: 系统 CPU 核心数 = $JOBS)
    -h, --help            显示此帮助

支持的平台:
    macOS     Homebrew (arm64 / x86_64)
    Linux     apt / dnf / yum / pacman / apk / zypper (含 WSL)
    Windows   choco / scoop / winget (Git Bash / MSYS2 / Cygwin)

示例:
    $0                              # 一键编译两者
    $0 --clean                      # 清理后重新编译
    $0 --skip-netlist               # 只编译 slang
    $0 --prefix /opt/navisv/bin     # 安装到指定目录

环境变量 (可选):
    CC, CXX                          自定义 C/C++ 编译器
    CMAKE_ARGS                       额外的 cmake 参数
EOF
}

# ── 参数解析 ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --debug)        BUILD_TYPE="Debug"; shift ;;
        --clean)        CLEAN_BUILD=1; shift ;;
        --skip-slang)   SKIP_SLANG=1; shift ;;
        --skip-netlist) SKIP_NETLIST=1; shift ;;
        --prefix)       PREFIX_DIR="$2"; shift 2 ;;
        --slang-dir)    SLANG_DIR="$2"; shift 2 ;;
        --netlist-dir)  NETLIST_DIR="$2"; shift 2 ;;
        --jobs)         JOBS="$2"; shift 2 ;;
        -h|--help)      usage; exit 0 ;;
        *)              err "未知参数: $1"; usage; exit 1 ;;
    esac
done

# ── 前置条件检查 ───────────────────────────────────────────────────────
check_prerequisites() {
    section "检查前置条件"

    # 平台检测
    detect_platform
    setup_script_path
    ok "检测到平台: $PLATFORM_DESC"
    if [[ -n "$PLATFORM_PKG_MGR" ]]; then
        info "包管理器: $PLATFORM_PKG_MGR"
    fi

    # 检测 CPU 核心数
    JOBS=$(detect_cpu_count)
    info "CPU 核心数: $JOBS"

    local missing=0
    for cmd in cmake git make; do
        if ! command -v "$cmd" &>/dev/null; then
            err "缺少命令: $cmd"
            missing=1
        fi
    done

    if [[ $missing -eq 1 ]]; then
        echo ""
        echo "请先安装缺失的工具:"
        echo -e "  ${GREEN}$PLATFORM_INSTALL_CMD${NC}"
        exit 1
    fi

    # 检查 C++ 编译器
    if ! command -v g++ &>/dev/null && ! command -v clang++ &>/dev/null; then
        # 在 MSYS2 / Git Bash 下检查
        if [[ "$PLATFORM_OS" == "windows" ]]; then
            if ! command -v gcc &>/dev/null && ! command -v cl &>/dev/null; then
                err "Windows 下缺少 C++ 编译器 (g++ 或 MSVC)"
                echo "  推荐: choco install mingw"
                exit 1
            fi
        else
            err "缺少 C++ 编译器 (g++ 或 clang++)"
            echo "  macOS:  xcode-select --install"
            echo "  Linux:  sudo apt install g++"
            exit 1
        fi
    fi

    local cxx_compiler
    if command -v clang++ &>/dev/null; then
        cxx_compiler="clang++"
    elif command -v g++ &>/dev/null; then
        cxx_compiler="g++"
    elif command -v cl &>/dev/null; then
        cxx_compiler="cl.exe (MSVC)"
    else
        cxx_compiler="unknown"
    fi
    ok "cmake, git, make, $cxx_compiler 都已安装"

    # 报告系统信息
    info "构建类型: $BUILD_TYPE"
    info "并行任务数: $JOBS"
    info "slang 目录: $SLANG_DIR"
    info "slang-netlist 目录: $NETLIST_DIR"
    if [[ -n "$PREFIX_DIR" ]]; then
        info "安装目录: $PREFIX_DIR"
    fi
}

# ── 克隆仓库 ───────────────────────────────────────────────────────────
clone_if_needed() {
    local repo_url=$1
    local target_dir=$2
    local repo_name=$3

    if [[ -d "$target_dir" ]]; then
        info "$repo_name 已存在: $target_dir"
        return 0
    fi

    info "克隆 $repo_name 到 $target_dir"
    git clone --depth 1 "$repo_url" "$target_dir"
    ok "$repo_name 克隆完成"
}

# ── 编译 slang ─────────────────────────────────────────────────────────
build_slang() {
    section "编译 slang (SystemVerilog 前端)"

    clone_if_needed "https://github.com/MikePopoloski/slang.git" "$SLANG_DIR" "slang"

    cd "$SLANG_DIR"

    # 清理选项
    if [[ $CLEAN_BUILD -eq 1 ]] && [[ -d build ]]; then
        info "清理 build 目录"
        rm -rf build
    fi

    # 配置
    info "配置 cmake (Build Type: $BUILD_TYPE)"
    if ! cmake -B build -DCMAKE_BUILD_TYPE="$BUILD_TYPE" ${CMAKE_ARGS:-} 2>&1 | tail -10; then
        err "cmake 配置失败"
        exit 1
    fi

    # 编译
    info "开始编译 (使用 $JOBS 个并行任务)..."
    if ! cmake --build build -j "$JOBS" 2>&1 | tail -5; then
        err "编译失败"
        exit 1
    fi

    # slang 的二进制在项目根目录 (CMake 自定义路径)
    # Windows 下可能带 .exe 后缀
    local slang_bin=""
    for candidate in \
        "$SLANG_DIR/slang${EXE_EXT}" \
        "$SLANG_DIR/build/bin/slang${EXE_EXT}" \
        "$SLANG_DIR/build/slang${EXE_EXT}" \
        "$SLANG_DIR/build/Release/slang${EXE_EXT}" \
        "$SLANG_DIR/build/Debug/slang${EXE_EXT}" \
        "$SLANG_DIR/slang" \
        "$SLANG_DIR/build/bin/slang" \
        "$SLANG_DIR/build/slang"; do
        if [[ -x "$candidate" ]]; then
            slang_bin="$candidate"
            break
        fi
    done

    if [[ -z "$slang_bin" ]]; then
        err "未找到 slang 二进制文件 (尝试了 .exe 变体)"
        exit 1
    fi

    # 测试
    info "测试 slang 二进制"
    "$slang_bin" --version

    ok "slang 编译完成: $slang_bin"
    SLANG_BIN="$slang_bin"
}

# ── 编译 slang-netlist ─────────────────────────────────────────────────
build_netlist() {
    section "编译 slang-netlist (网表提取工具)"

    clone_if_needed "https://github.com/MikePopoloski/slang-netlist.git" "$NETLIST_DIR" "slang-netlist"

    # slang-netlist 依赖 slang, 检查 SLANG_BIN
    if [[ -z "${SLANG_BIN:-}" ]] || [[ ! -x "${SLANG_BIN}" ]]; then
        # 尝试从默认位置找
        if [[ -x "$SLANG_DIR/slang" ]]; then
            SLANG_BIN="$SLANG_DIR/slang"
            warn "使用默认 slang 路径: $SLANG_BIN"
        else
            err "找不到 slang 二进制,无法编译 slang-netlist"
            echo "请先编译 slang (移除 --skip-slang 选项)"
            exit 1
        fi
    fi

    cd "$NETLIST_DIR"

    # 清理选项
    if [[ $CLEAN_BUILD -eq 1 ]] && [[ -d build ]]; then
        info "清理 build 目录"
        rm -rf build
    fi

    # 配置
    info "配置 cmake (Build Type: $BUILD_TYPE)"
    info "slang 二进制: $SLANG_BIN"
    if ! cmake -B build \
        -DCMAKE_BUILD_TYPE="$BUILD_TYPE" \
        -DSLANG_EXECUTABLE="$SLANG_BIN" \
        ${CMAKE_ARGS:-} 2>&1 | tail -10; then
        err "cmake 配置失败"
        exit 1
    fi

    # 编译
    info "开始编译 (使用 $JOBS 个并行任务)..."
    if ! cmake --build build -j "$JOBS" 2>&1 | tail -5; then
        err "编译失败"
        exit 1
    fi

    # slang-netlist 的二进制在 build/tools/driver/ 下
    # Windows 下可能带 .exe 后缀
    local netlist_bin=""
    for candidate in \
        "$NETLIST_DIR/build/tools/driver/slang-netlist${EXE_EXT}" \
        "$NETLIST_DIR/build/bin/slang-netlist${EXE_EXT}" \
        "$NETLIST_DIR/build/Release/slang-netlist${EXE_EXT}" \
        "$NETLIST_DIR/build/Debug/slang-netlist${EXE_EXT}" \
        "$NETLIST_DIR/build/tools/driver/slang-netlist" \
        "$NETLIST_DIR/build/bin/slang-netlist"; do
        if [[ -x "$candidate" ]]; then
            netlist_bin="$candidate"
            break
        fi
    done

    if [[ -z "$netlist_bin" ]]; then
        err "未找到 slang-netlist 二进制文件 (尝试了 .exe 变体)"
        exit 1
    fi

    # 测试
    info "测试 slang-netlist 二进制"
    "$netlist_bin" --version 2>/dev/null || true
    if "$netlist_bin" --help 2>&1 | grep -q "slang-netlist"; then
        ok "slang-netlist 二进制验证通过"
    else
        warn "slang-netlist 二进制可能未正确编译"
    fi

    ok "slang-netlist 编译完成: $netlist_bin"
    NETLIST_BIN="$netlist_bin"
}

# ── 安装到 prefix ──────────────────────────────────────────────────────
install_to_prefix() {
    if [[ -z "$PREFIX_DIR" ]]; then
        return 0
    fi

    section "安装到 $PREFIX_DIR"
    mkdir -p "$PREFIX_DIR"

    if [[ -n "${SLANG_BIN:-}" ]] && [[ -x "$SLANG_BIN" ]]; then
        cp "$SLANG_BIN" "$PREFIX_DIR/slang${EXE_EXT}"
        ok "已安装 slang → $PREFIX_DIR/slang${EXE_EXT}"
    fi

    if [[ -n "${NETLIST_BIN:-}" ]] && [[ -x "$NETLIST_BIN" ]]; then
        cp "$NETLIST_BIN" "$PREFIX_DIR/slang-netlist${EXE_EXT}"
        ok "已安装 slang-netlist → $PREFIX_DIR/slang-netlist${EXE_EXT}"
    fi
}

# ── 写环境变量文件 ────────────────────────────────────────────────────
write_env_file() {
    local env_file="$PWD/.navisv_env"
    section "写入环境变量到 $env_file"

    cat > "$env_file" <<EOF
# navisv 环境变量 (由 install_dependencies.sh 生成)
# 用法: source .navisv_env

export NAVISV_SLANG_BIN="${SLANG_BIN:-}"
export NAVISV_NETLIST_BIN="${NETLIST_BIN:-}"
EOF

    ok "环境变量文件已生成"
    cat "$env_file"
}

# ── 打印最终信息 ──────────────────────────────────────────────────────
print_summary() {
    section "安装完成 ✅"

    echo ""
    echo "二进制路径:"
    echo "  slang:         ${SLANG_BIN:-N/A}"
    echo "  slang-netlist: ${NETLIST_BIN:-N/A}"
    echo ""

    echo "下次使用 navisv 前,请设置环境变量:"
    echo ""
    echo -e "  ${GREEN}source .navisv_env${NC}    # 当前会话"
    echo ""
    echo "或永久生效 (加到 $SHELL_RC):"
    echo ""
    echo "  export NAVISV_SLANG_BIN=\"${SLANG_BIN:-}\""
    echo "  export NAVISV_NETLIST_BIN=\"${NETLIST_BIN:-}\""
    echo ""

    # Windows 额外提示
    if [[ "$PLATFORM_OS" == "windows" ]]; then
        echo "Windows 下设置环境变量的方式:"
        echo "  1. PowerShell (当前会话):"
        echo "     \$env:NAVISV_SLANG_BIN = '${SLANG_BIN:-}'"
        echo "     \$env:NAVISV_NETLIST_BIN = '${NETLIST_BIN:-}'"
        echo "  2. 系统设置 (永久):"
        echo "     setx NAVISV_SLANG_BIN \"${SLANG_BIN:-}\""
        echo "     setx NAVISV_NETLIST_BIN \"${NETLIST_BIN:-}\""
        echo ""
    fi

    # 验证
    if [[ -n "${SLANG_BIN:-}" ]] && [[ -n "${NETLIST_BIN:-}" ]]; then
        info "验证 navisv 配置..."
        export NAVISV_SLANG_BIN="$SLANG_BIN"
        export NAVISV_NETLIST_BIN="$NETLIST_BIN"
        if command -v navisv &>/dev/null; then
            if navisv tools 2>&1 | grep -q "✓\|✅"; then
                ok "navisv 工具检查通过"
            fi
        else
            info "提示: 安装 navisv 后运行 'navisv tools' 验证"
        fi
    fi
}

# ── 主流程 ────────────────────────────────────────────────────────────
main() {
    check_prerequisites

    if [[ $SKIP_SLANG -eq 0 ]]; then
        build_slang
    else
        warn "跳过 slang 编译 (使用现有 $SLANG_DIR/slang)"
        if [[ -x "$SLANG_DIR/slang" ]]; then
            SLANG_BIN="$SLANG_DIR/slang"
        fi
    fi

    if [[ $SKIP_NETLIST -eq 0 ]]; then
        build_netlist
    else
        warn "跳过 slang-netlist 编译"
        if [[ -x "$NETLIST_DIR/build/tools/driver/slang-netlist" ]]; then
            NETLIST_BIN="$NETLIST_DIR/build/tools/driver/slang-netlist"
        fi
    fi

    install_to_prefix
    write_env_file
    print_summary
}

main

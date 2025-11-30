#!/bin/bash

# 游戏卡死问题诊断脚本
# 用于检查可能导致日志锁竞争的代码模式

echo "=========================================="
echo "游戏卡死问题 - 日志诊断脚本"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# 检查是否有源代码目录
if [ ! -d "src" ] && [ ! -d "app" ] && [ ! -d "android" ]; then
    echo -e "${YELLOW}警告: 未找到源代码目录，将搜索当前目录${NC}"
    SEARCH_DIR="."
else
    SEARCH_DIR="."
fi

echo "1. 搜索所有日志调用..."
echo "----------------------------------------"
LOG_COUNT=$(find "$SEARCH_DIR" -type f \( -name "*.java" -o -name "*.kt" -o -name "*.cpp" -o -name "*.c" \) 2>/dev/null | xargs grep -E "\.(d|i|v|w|e)\(|Log\.(d|i|v|w|e)" 2>/dev/null | wc -l)
echo -e "找到 ${GREEN}$LOG_COUNT${NC} 个日志调用"

if [ "$LOG_COUNT" -gt 0 ]; then
    echo ""
    echo "前20个日志调用位置:"
    find "$SEARCH_DIR" -type f \( -name "*.java" -o -name "*.kt" -o -name "*.cpp" -o -name "*.c" \) 2>/dev/null | xargs grep -nE "\.(d|i|v|w|e)\(|Log\.(d|i|v|w|e)" 2>/dev/null | head -20
fi

echo ""
echo "2. 搜索Insets相关代码..."
echo "----------------------------------------"
INSETS_COUNT=$(find "$SEARCH_DIR" -type f \( -name "*.java" -o -name "*.kt" \) 2>/dev/null | xargs grep -i "insets\|Insets" 2>/dev/null | wc -l)
echo -e "找到 ${GREEN}$INSETS_COUNT${NC} 个Insets相关代码位置"

if [ "$INSETS_COUNT" -gt 0 ]; then
    echo ""
    echo "Insets相关代码位置:"
    find "$SEARCH_DIR" -type f \( -name "*.java" -o -name "*.kt" \) 2>/dev/null | xargs grep -in "insets\|Insets" 2>/dev/null | head -20
fi

echo ""
echo "3. 检查关键方法..."
echo "----------------------------------------"
KEY_METHODS=("applyLocalVisibilityOverride" "onInsetsStateChanged" "onStateChanged" "insetsControlChanged")

for method in "${KEY_METHODS[@]}"; do
    echo "搜索方法: $method"
    find "$SEARCH_DIR" -type f \( -name "*.java" -o -name "*.kt" \) 2>/dev/null | xargs grep -n "$method" 2>/dev/null | head -5
    echo ""
done

echo ""
echo "4. 检查日志级别配置..."
echo "----------------------------------------"
if [ -f "build.gradle" ] || [ -f "app/build.gradle" ]; then
    echo "检查 build.gradle 中的日志配置:"
    grep -i "log\|debug" build.gradle app/build.gradle 2>/dev/null | head -10
else
    echo "未找到 build.gradle 文件"
fi

echo ""
echo "5. 建议的修复步骤..."
echo "----------------------------------------"
echo "1. 检查上述日志调用，特别是Insets相关代码中的日志"
echo "2. 移除或注释掉非关键日志，特别是DEBUG和VERBOSE级别"
echo "3. 确保生产版本中禁用详细日志"
echo "4. 考虑使用条件编译或日志级别控制"

echo ""
echo "=========================================="
echo "诊断完成"
echo "=========================================="

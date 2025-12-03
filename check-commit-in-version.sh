#!/bin/bash

# 检查代码是否合入某个版本的实用脚本
# 使用方法: ./check-commit-in-version.sh <commit-hash> [branch-name|tag-name]

COMMIT_HASH=$1
TARGET_VERSION=$2

if [ -z "$COMMIT_HASH" ]; then
    echo "用法: $0 <commit-hash> [branch-name|tag-name]"
    echo ""
    echo "示例:"
    echo "  $0 abc1234              # 检查提交在哪些分支和标签中"
    echo "  $0 abc1234 main         # 检查提交是否在main分支中"
    echo "  $0 abc1234 v1.0.0       # 检查提交是否在v1.0.0标签中"
    exit 1
fi

# 验证提交是否存在
if ! git cat-file -e "$COMMIT_HASH" 2>/dev/null; then
    echo "错误: 提交 $COMMIT_HASH 不存在"
    exit 1
fi

echo "=========================================="
echo "检查提交: $COMMIT_HASH"
echo "提交信息: $(git log -1 --oneline $COMMIT_HASH)"
echo "=========================================="
echo ""

if [ -z "$TARGET_VERSION" ]; then
    # 如果没有指定目标版本，显示所有包含该提交的分支和标签
    
    echo "【包含此提交的分支】"
    echo "----------------------------------------"
    BRANCHES=$(git branch -a --contains $COMMIT_HASH)
    if [ -n "$BRANCHES" ]; then
        echo "$BRANCHES" | sed 's/^/  /'
    else
        echo "  无"
    fi
    echo ""
    
    echo "【包含此提交的标签】"
    echo "----------------------------------------"
    TAGS=$(git tag --contains $COMMIT_HASH)
    if [ -n "$TAGS" ]; then
        echo "$TAGS" | sed 's/^/  /'
    else
        echo "  无"
    fi
    echo ""
    
    # 检查是否在main分支
    if git branch -a --contains $COMMIT_HASH | grep -qE "(main|origin/main)"; then
        echo "✓ 已在 main 分支中"
    else
        echo "✗ 不在 main 分支中"
    fi
    
else
    # 检查是否在指定的分支或标签中
    echo "检查是否在: $TARGET_VERSION"
    echo "----------------------------------------"
    
    # 先尝试作为分支检查
    if git show-ref --verify --quiet refs/heads/$TARGET_VERSION || \
       git show-ref --verify --quiet refs/remotes/origin/$TARGET_VERSION; then
        if git branch -a --contains $COMMIT_HASH | grep -qE "$TARGET_VERSION"; then
            echo "✓ 提交已在分支 '$TARGET_VERSION' 中"
            echo ""
            echo "提交在分支中的位置:"
            git log $TARGET_VERSION --oneline | grep -B 5 -A 5 "$COMMIT_HASH" | head -10
        else
            echo "✗ 提交不在分支 '$TARGET_VERSION' 中"
        fi
    # 再尝试作为标签检查
    elif git show-ref --verify --quiet refs/tags/$TARGET_VERSION; then
        if git tag --contains $COMMIT_HASH | grep -q "$TARGET_VERSION"; then
            echo "✓ 提交已在标签 '$TARGET_VERSION' 中"
            echo ""
            echo "标签信息:"
            git show $TARGET_VERSION --no-patch --format="  标签: %D%n  提交: %H%n  日期: %ai%n  作者: %an"
        else
            echo "✗ 提交不在标签 '$TARGET_VERSION' 中"
            echo ""
            echo "标签信息:"
            git show $TARGET_VERSION --no-patch --format="  标签: %D%n  提交: %H%n  日期: %ai"
            echo ""
            echo "提示: 标签指向的提交是 $(git rev-parse $TARGET_VERSION)"
        fi
    else
        echo "错误: '$TARGET_VERSION' 既不是有效的分支也不是有效的标签"
        echo ""
        echo "可用的分支:"
        git branch -a | head -10
        echo ""
        echo "可用的标签:"
        git tag | head -10
        exit 1
    fi
fi

echo ""
echo "=========================================="

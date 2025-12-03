#!/bin/bash
# 检查提交是否在某个版本（分支或标签）中的脚本

COMMIT_HASH=$1
VERSION=$2  # 可以是分支名或标签名

if [ -z "$COMMIT_HASH" ] || [ -z "$VERSION" ]; then
    echo "用法: $0 <commit-hash> <branch-or-tag>"
    echo ""
    echo "示例:"
    echo "  $0 26c2364 main"
    echo "  $0 26c2364 v1.0.0"
    exit 1
fi

echo "=========================================="
echo "检查提交是否在版本中"
echo "=========================================="
echo "提交哈希: $COMMIT_HASH"
echo "版本/分支/标签: $VERSION"
echo ""

# 验证提交是否存在
if ! git cat-file -e "$COMMIT_HASH" 2>/dev/null; then
    echo "错误: 提交 $COMMIT_HASH 不存在"
    exit 1
fi

# 显示提交信息
echo "提交信息:"
git log -1 "$COMMIT_HASH" --oneline
echo ""

# 检查是否在分支中
FOUND_IN_BRANCH=false
if git branch -a | grep -q "$VERSION"; then
    if git branch -a --contains "$COMMIT_HASH" | grep -q "$VERSION"; then
        echo "✓ 提交 $COMMIT_HASH 在分支 $VERSION 中"
        FOUND_IN_BRANCH=true
    else
        echo "✗ 提交 $COMMIT_HASH 不在分支 $VERSION 中"
    fi
fi

# 检查是否在标签中
FOUND_IN_TAG=false
if git tag | grep -q "^$VERSION$"; then
    if git tag --contains "$COMMIT_HASH" | grep -q "^$VERSION$"; then
        echo "✓ 提交 $COMMIT_HASH 在标签 $VERSION 中"
        FOUND_IN_TAG=true
    else
        echo "✗ 提交 $COMMIT_HASH 不在标签 $VERSION 中"
    fi
fi

# 如果既不是分支也不是标签，尝试直接检查
if [ "$FOUND_IN_BRANCH" = false ] && [ "$FOUND_IN_TAG" = false ]; then
    # 尝试作为 ref 检查
    if git rev-parse --verify "$VERSION" >/dev/null 2>&1; then
        if git log "$VERSION" --oneline | grep -q "$COMMIT_HASH"; then
            echo "✓ 提交 $COMMIT_HASH 在 $VERSION 中"
        else
            echo "✗ 提交 $COMMIT_HASH 不在 $VERSION 中"
        fi
    else
        echo "警告: $VERSION 不是有效的分支或标签"
        echo ""
        echo "可用的分支:"
        git branch -a | head -10
        echo ""
        echo "可用的标签:"
        git tag | head -10
    fi
fi

echo ""
echo "=========================================="
echo "该提交所在的所有分支:"
git branch -a --contains "$COMMIT_HASH" | head -10
echo ""
echo "该提交所在的所有标签:"
git tag --contains "$COMMIT_HASH" | head -10

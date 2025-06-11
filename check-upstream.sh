#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

UPSTREAM_REPO="letta-ai/letta"

echo -e "${BLUE}👀 Letta Upstream Check${NC}"
echo "======================="

# Check if we're in a git repo
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${RED}❌ Not in a git repository${NC}"
    exit 1
fi

# Add upstream remote if it doesn't exist
if ! git remote get-url upstream > /dev/null 2>&1; then
    echo -e "${YELLOW}➕ Adding upstream remote...${NC}"
    git remote add upstream https://github.com/$UPSTREAM_REPO.git
fi

# Fetch from upstream
echo -e "${BLUE}📥 Fetching from upstream...${NC}"
git fetch upstream --quiet

# Check how far behind we are
BEHIND_COUNT=$(git rev-list --count HEAD..upstream/main)

if [ $BEHIND_COUNT -eq 0 ]; then
    echo -e "${GREEN}✅ Up to date with upstream${NC}"
else
    echo -e "${YELLOW}📈 $BEHIND_COUNT commits behind upstream/main${NC}"
    
    echo -e "\n${BLUE}📝 New commits in upstream:${NC}"
    git log --oneline --color=always HEAD..upstream/main
    
    echo -e "\n${BLUE}📊 File changes summary:${NC}"
    git diff --stat HEAD upstream/main
fi

# Show recent releases
echo -e "\n${BLUE}🏷️  Recent releases:${NC}"
gh release list --repo $UPSTREAM_REPO --limit 3 2>/dev/null || echo "Run 'gh auth login' to see releases"

# Show current branch info
echo -e "\n${BLUE}📍 Current branch: ${YELLOW}$(git branch --show-current)${NC}"
echo -e "${BLUE}📊 Working tree status:${NC}"
git status --short

echo -e "\n${GREEN}Run './sync-upstream.sh' to merge changes${NC}"
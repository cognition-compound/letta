#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
UPSTREAM_REMOTE="upstream"
UPSTREAM_REPO="letta-ai/letta"
FORK_REMOTE="origin"
MAIN_BRANCH="main"
DEV_BRANCH="dev"

# Parse command line options
AUTO_MERGE=false
AUTO_PUSH=false
SYNC_DEV=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --auto-merge)
            AUTO_MERGE=true
            shift
            ;;
        --auto-push)
            AUTO_PUSH=true
            shift
            ;;
        --sync-dev)
            SYNC_DEV=true
            shift
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  --auto-merge    Automatically merge upstream changes"
            echo "  --auto-push     Automatically push changes to origin"
            echo "  --sync-dev      Also sync dev branch with main"
            echo "  --help          Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}🔄 Letta Upstream Sync Tool (Auto Mode)${NC}"
echo "=========================================="

# Check if we're in a git repo
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${RED}❌ Not in a git repository${NC}"
    exit 1
fi

# Add upstream remote if it doesn't exist
if ! git remote get-url $UPSTREAM_REMOTE > /dev/null 2>&1; then
    echo -e "${YELLOW}➕ Adding upstream remote...${NC}"
    git remote add $UPSTREAM_REMOTE https://github.com/$UPSTREAM_REPO.git
fi

# Fetch from upstream
echo -e "${BLUE}📥 Fetching from upstream...${NC}"
git fetch $UPSTREAM_REMOTE

# Get current branch
CURRENT_BRANCH=$(git branch --show-current)
echo -e "${BLUE}📍 Current branch: ${YELLOW}$CURRENT_BRANCH${NC}"

# Show what's new in upstream
echo -e "\n${BLUE}📊 Changes in upstream since last sync:${NC}"
BEHIND_COUNT=$(git rev-list --count HEAD..upstream/$MAIN_BRANCH)
if [ $BEHIND_COUNT -eq 0 ]; then
    echo -e "${GREEN}✅ Already up to date with upstream${NC}"
    exit 0
else
    echo -e "${YELLOW}📈 $BEHIND_COUNT commits behind upstream${NC}"
    
    # Show recent upstream commits
    echo -e "\n${BLUE}📝 Recent upstream commits:${NC}"
    git log --oneline --color=always HEAD..upstream/$MAIN_BRANCH | head -10
    
    # Show upstream releases if any
    echo -e "\n${BLUE}🏷️  Recent upstream releases:${NC}"
    gh release list --repo $UPSTREAM_REPO --limit 5 2>/dev/null || echo "No releases found or gh auth needed"
fi

# Function to sync a branch automatically
sync_branch_auto() {
    local branch=$1
    local target_branch=${2:-$branch}
    
    echo -e "\n${BLUE}🔄 Syncing $branch branch...${NC}"
    
    # Switch to target branch
    if git show-ref --verify --quiet refs/heads/$branch; then
        git checkout $branch
        echo -e "${BLUE}📍 Switched to $branch${NC}"
        
        # Show diff before merging
        if [ $BEHIND_COUNT -gt 0 ]; then
            echo -e "\n${BLUE}📋 Changes that will be merged:${NC}"
            git diff --stat HEAD upstream/$target_branch
            
            if [ "$AUTO_MERGE" = true ]; then
                echo -e "${BLUE}🔀 Auto-merging upstream/$target_branch into $branch...${NC}"
                if git merge upstream/$target_branch; then
                    echo -e "${GREEN}✅ Successfully merged upstream changes${NC}"
                    
                    # Push if auto-push is enabled
                    if [ "$AUTO_PUSH" = true ]; then
                        git push $FORK_REMOTE $branch
                        echo -e "${GREEN}✅ Pushed to origin/$branch${NC}"
                    else
                        echo -e "${YELLOW}ℹ️  Run 'git push origin $branch' to push changes${NC}"
                    fi
                else
                    echo -e "${RED}❌ Merge failed - please resolve conflicts manually${NC}"
                    return 1
                fi
            else
                echo -e "${YELLOW}ℹ️  Run with --auto-merge to automatically merge changes${NC}"
                echo -e "${YELLOW}ℹ️  Or manually run: git merge upstream/$target_branch${NC}"
            fi
        fi
    else
        echo -e "${YELLOW}⚠️  Branch $branch doesn't exist locally${NC}"
    fi
}

# Sync main branch
sync_branch_auto $MAIN_BRANCH

# Sync dev branch if requested and it exists
if [ "$SYNC_DEV" = true ] && git show-ref --verify --quiet refs/heads/$DEV_BRANCH; then
    echo -e "\n${BLUE}🔄 Syncing dev branch with main...${NC}"
    git checkout $DEV_BRANCH
    
    # Show what would be merged from main
    echo -e "${BLUE}📋 Changes from main to dev:${NC}"
    git diff --stat HEAD main
    
    if [ "$AUTO_MERGE" = true ]; then
        if git merge main; then
            echo -e "${GREEN}✅ Successfully merged main into dev${NC}"
            
            if [ "$AUTO_PUSH" = true ]; then
                git push $FORK_REMOTE $DEV_BRANCH
                echo -e "${GREEN}✅ Pushed to origin/dev${NC}"
            else
                echo -e "${YELLOW}ℹ️  Run 'git push origin dev' to push changes${NC}"
            fi
        else
            echo -e "${RED}❌ Merge failed - please resolve conflicts manually${NC}"
        fi
    else
        echo -e "${YELLOW}ℹ️  Run with --auto-merge to automatically merge main into dev${NC}"
        echo -e "${YELLOW}ℹ️  Or manually run: git merge main${NC}"
    fi
fi

# Return to original branch
if [ "$CURRENT_BRANCH" != "$(git branch --show-current)" ]; then
    git checkout $CURRENT_BRANCH
    echo -e "\n${BLUE}🔙 Returned to $CURRENT_BRANCH${NC}"
fi

echo -e "\n${GREEN}🎉 Sync complete!${NC}"

# Show current status
echo -e "\n${BLUE}📊 Current status:${NC}"
git status --short
# Git Steps

## Go to your project path
cd /path/to/your-project

## Connect to remote branch as origin
git remote add origin https://github.com/username/repo.git

## If origin already exists but has the wrong URL:
git remote set-url origin https://github.com/USERNAME/REPOSITORY.git

## get clone repository for new project setup on local
git clone <repository-url>
cd <repository-folder>

## Existing local project, no local changes
git switch main
git pull origin main

## Fetch remote branches.
git fetch origin
git branch -r


# Repeat these steps for every new feature

## Get the latest main
git switch main
git pull origin main

## Create a feature branch for feature branch development
git switch -c feature_n#

## Develop and test
Make your code changes in VS Code. Run your tests and check which files have changed:
git status
git diff

## add your changes
git add .

## Commit your changes
git commit -m "your changes"


## switch local branch as main / feature
git branch -M main

## if feature branch then 
git branch -b main



## now push your changes from local to remote
git push -u origin main



## In case of error with push:
git pull origin main --rebase

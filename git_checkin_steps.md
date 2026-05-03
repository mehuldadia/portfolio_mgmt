## Go to your project path
cd /path/to/your-project

## add your changes
git add .

## Commit your changes
git commit -m "your changes"


## switch local branch as main / feature
git branch -M main

## if feature branch then 
git branch -b main

## Connect to remote branch as origin
git remote add origin https://github.com/username/repo.git


## now push your changes from local to remote
git push -u origin main



## In case of error with push:
git pull origin main --rebase

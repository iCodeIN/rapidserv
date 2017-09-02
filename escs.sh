##############################################################################
# push, rapidserv, github.
cd ~/projects/rapidserv-code
git status
git add *
git commit -a
git push 
##############################################################################
cd ~/projects/rapidserv-code
git pull
##############################################################################
# create the develop branch, rapidserv.
git branch -a
git checkout -b development
git push --set-upstream origin development
##############################################################################
# merge master into development, rapidserv.
cd ~/projects/rapidserv-code
git checkout development
git merge master
git push
##############################################################################
# merge development into master, rapidserv.
cd ~/projects/rapidserv-code
git checkout master
git merge development
git push
git checkout development
##############################################################################
# check diffs, rapidserv.
cd ~/projects/rapidserv-code
git diff
##############################################################################
# delete the development branch, rapidserv.
git branch -d development
git push origin :development
git fetch -p 
##############################################################################
# undo, changes, rapidserv, github.
cd ~/projects/rapidserv-code
git checkout *
##############################################################################
# install, rapidserv.
sudo bash -i
cd /home/tau/projects/rapidserv-code
python2 setup.py install
rm -fr build
exit
##############################################################################
# build, rapidserv, package, disutils.
cd /home/tau/projects/rapidserv-code
python2.6 setup.py sdist 
rm -fr dist
rm MANIFEST
##############################################################################
# share, put, place, host, package, python, pip, application, rapidserv.

cd ~/projects/rapidserv-code
python2 setup.py sdist register upload
rm -fr dist
##############################################################################
# delete, remove, clean, *.pyc files, vy, vyapp.
cd /home/tau/projects/rapidserv-code/
find . -name "*.pyc" -exec rm -f {} \;







crud: copycrud
	@zip -r package.zip python
	echo "Removing file from python lib folder"
	@rm -rf ./python/
copycrud:
	echo "Copying file to python lib folder"
	@mkdir -p ./python/lib/python3.9/site-packages/
	@cp ./crud.py ./python/lib/python3.9/site-packages/

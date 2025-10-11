# Okular Bookmarks to PDF (ob2pdf)

OB2PDF is a Python script to save Okular's bookmarks into the actual PDF file,
so that you can view them in other PDF readers.

Install the dependencies:
```shell
pip install pypdf
```

Run the script as:
```shell
python3 ob2pdf.py <path/to/file.pdf>
```

If the Okular bookmarks file `bookmarks.xml` is not found, you must specify its path:
```shell
python3 ob2pdf.py <path/to/file.pdf> <path/to/bookmarks.xlm>
```

It will return a copy of your file with all your bookmarks included.

That's it! Enjoy :D


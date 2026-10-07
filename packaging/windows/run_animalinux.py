"""Punto de entrada del ejecutable de Windows (PyInstaller)."""
import sys

from animalinux.app import main

if __name__ == "__main__":
    sys.exit(main())

import subprocess
import sys
from setuptools import setup
from setuptools.command.develop import develop
from setuptools.command.install import install


def _install_chromium():
    print("Installing Playwright Chromium browser...")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=False,
    )
    if result.returncode == 0:
        print("Playwright Chromium installed successfully.")
    else:
        print("Warning: playwright install chromium failed (exit code %d). Run it manually." % result.returncode)


class PostDevelop(develop):
    def run(self):
        develop.run(self)
        _install_chromium()


class PostInstall(install):
    def run(self):
        install.run(self)
        _install_chromium()


setup(
    name="playwright-chromium-setup",
    version="1.0.0",
    description="Post-install hook to download Playwright Chromium browser binaries.",
    install_requires=["playwright"],
    cmdclass={
        "develop": PostDevelop,
        "install": PostInstall,
    },
)

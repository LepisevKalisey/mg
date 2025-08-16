#!/usr/bin/env python3

from setuptools import setup, find_packages

with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setup(
    name='mg-digest-bot',
    version='0.1.0',
    description='Telegram digest bot for creating summary channels',
    author='MG Team',
    packages=find_packages(),
    python_requires='>=3.11',
    install_requires=requirements,
    entry_points={
        'console_scripts': [
            'mg-bot=app.bot.main:main',
            'mg-watcher=app.watcher:main',
            'mg-worker=app.worker.scheduler:main',
            'mg-web=app.web:main',
            'mg-all=run_all:main',
        ],
    },
)
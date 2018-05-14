from setuptools import setup, find_packages
import sdscli


setup(
    name='sdscli',
    version=sdscli.__version__,
    long_description=sdscli.__description__,
    url=sdscli.__url__,
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=[ 'distribute', 'pyyaml', 'pygments', 'prompt-toolkit', 
                       'fabric', 'tqdm==4.19.7', 'backoff', 'azure-mgmt-compute' ],
    entry_points={
        'console_scripts': [
            'sds=sdscli.command_line:main'
        ]
    },
    package_data={
        '': [ 'adapters/hysds/files/*', 'adapters/hysds/files/*/*',
              'adapters/sdskit/files/*', 'adapters/sdskit/files/*/*' ],
    }
)

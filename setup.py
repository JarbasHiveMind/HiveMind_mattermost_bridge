from setuptools import setup

setup(
    name='HiveMind-mattermost-bridge',
    version='0.2.0',
    packages=['mattermost_bridge'],
    url='https://github.com/JarbasHiveMind/HiveMind_mattermost_bridge',
    license='Apache-2.0',
    author='jarbasAI',
    author_email='jarbasai@mailfence.com',
    description='Mattermost bridge for HiveMind',
    long_description=open('readme.md').read() if __import__('os').path.exists('readme.md') else '',
    long_description_content_type='text/markdown',
    install_requires=[
        # Async client lives behind the [async] extra; pin floor at the
        # release that first ships AsyncHiveMessageBusClient.
        "hivemind_bus_client[async]>=0.8.0",
        "mattermostdriver",
        "ovos-bus-client>=1.3.1",
        "ovos_utils",
        "click",
    ],
    extras_require={
        "test": ["pytest"],
    },
    entry_points={
        'console_scripts': [
            'hm-mattermost-bridge=mattermost_bridge.__main__:launch_bot'
        ]
    },
)

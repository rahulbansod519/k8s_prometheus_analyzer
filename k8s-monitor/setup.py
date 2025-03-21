from setuptools import setup, find_packages

setup(
    name="k8s_prometheus_analyzer",
    version="0.1",
    packages=find_packages(),  # Automatically finds `k8s_prometheus_analyzer`
    install_requires=[
        "requests",
        "tabulate"
    ],
    entry_points={
        "console_scripts": [
            "k8s-analyze=k8s_prometheus_analyzer.monitor:main"
        ]
    },
    author="Rahul Bansod",
    description="CLI tool to analyze Kubernetes resource usage from Prometheus and provide optimization suggestions.",
    url="https://github.com/rahulbansod519/k8s_prometheus_analyzer",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)

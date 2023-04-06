from setuptools import setup

setup(
    name="antiscope",
    version="0.2.0",
    packages=["antiscope"],
    py_modules=[
        "antiscope.__init__",
        "antiscope.dynamic",
        "antiscope.evocation",
        "antiscope.irrealis",
        "antiscope.openai_settings",
        "antiscope.openai_utils",
        "antiscope.utilz",
    ],
)

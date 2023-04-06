# antiscope

_antiscope - n. - If a microscope helps you see small things, and a 
telescope helps you see distant things, what does an antiscope help you see?_

### What is `antiscope`?

Have you ever wanted to combine the best features of functional programming 
and Zen koans? antiscope is a Python-language library that provides 
structures for irrealis programming. Irrealis programming permits evaluation 
of code in which some objects are undefined or incompletely defined. 
The program will run as if those objects were well-defined. (You could say 
that these objects are in a subjunctive mood, or that they are 
counterfactual, or that they are defined using possible-worlds semantics.)

For a more complete description, including many worked examples, please see 
the [introductory document here](https://github.com/MillionConcepts/antiscope/blob/main/introducing_antiscope.pdf).

### API KEY

To use this repository, you will need an OpenAI API key and organization 
defined in the variables `OPENAI_API_KEY` and `OPENAI_ORGANIZATION` in a 
file named `api_secrets.py` to be placed in the root directory of this 
repository. If you can't figure out what the previous sentence means, then 
you should probably not use this repository. Pakitamoq!

### Installation

You can use the [environment.yml](environment.yml) file to construct a 
conda environment with the dependencies you need to run `antiscope`.
The setup.py file is intended to facilitate editable installation into a 
working conda environment. It has no dependency specifications. 

### **Warning! Achtung!**

Use of this repository might cost you money or sanity. 
**It sometimes executes untrusted code _by design_**. 
We do not believe that the code in this repository is fit for any purpose. 
We recommend that you do not use it. We disclaim all responsibility for bad 
things that might happen if you use it anyway.
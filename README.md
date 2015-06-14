Super Settings
======================

Multi file config parser for projects.  Although this library was specifically designed to fix issues with large
django deployments with many, many settings, this can be used outside of django to setup settings for any python
project.  It does not rely on any outside libraries.  

The Problem
--------------
Django settings are great but as projects get big, settings management gets crazy.  You end up with:
* development settings
* app settings
* system settings
* production settings
* and the wonderful local settings

These become impossible to maintain over many environments and machines.  
This small library was made to solve this problem.  

How it works
---------------
Behind the scenes we use the configparser library to parse many files to render settings depending on the local config files.  

You pass in a `file_name` and a default config file and it merges three files together in the following order:

# default file: loaded first and should provide default values for all settings.  This is usually part of your code repo.
# /etc/default/{{file_name}}: Adds system wide defaults, different from the values in the repo.
# ~/.{{file_name}}: These are user values that override the system defaults.

You can add extra config files by calling `add_config_file` on a MultiFileConfigParser.  Anything you add will override 
values from the previous files.  The `add_config_file` method takes in the kwarg `required`.  By default config files
are not required and will just be skipped if they don't exist (program shouldn't fail because you don't create a ~/.{{file_name}}).  
If you make the config file required, it will raise a `ValueError` if the file doesn't exist.


Configuration Files
------------------------------
For help with config files please see:
https://docs.python.org/3.4/library/configparser.html

By default we use the ExtendedInterpolation so you can reference other variables and sections.  

Code Example
-----------------------
Below would load the following configuration files:

# /path/to/my/default.config
# /etc/default/mysettings
# ~/.mysettings


    import os
    from supersettings import MultiFileConfigParser
    parser = MultiFileConfigParser('mysettings', '/path/to/my/default.config')


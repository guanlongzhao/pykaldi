#!/usr/bin/env python
"""Setup configuration."""

from setuptools import setup, Extension, distutils, Command, find_packages
import distutils.command.build
import setuptools.command.build_ext
import setuptools.command.install
import setuptools.command.develop
import setuptools.command.build_py
import platform
import subprocess
import shutil
import sys
import os


################################################################################
# https://stackoverflow.com/questions/377017/test-if-executable-exists-in-python
################################################################################
def which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)
    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ['PATH'].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file
    return None

################################################################################
# Check variables / find programs
################################################################################
DEBUG = os.getenv('DEBUG') in ['ON', '1', 'YES', 'TRUE', 'Y']
PYCLIF = which("pyclif")
CWD = os.path.dirname(os.path.abspath(__file__))

if not PYCLIF:
  PYCLIF = os.getenv("PYCLIF")
  if not PYCLIF:
      print("We could not find PYCLIF. Forgot to activate venv?")
      sys.exit(1)

if "KALDI_DIR" not in os.environ:
  print("KALDI_DIR environment variable is not set.")
  sys.exit(1)
KALDI_DIR = os.environ['KALDI_DIR']
KALDI_SRC_DIR = os.path.join(KALDI_DIR, 'src')
KALDI_LIB_DIR = os.path.join(KALDI_DIR, 'src/lib')

CLIF_DIR = os.path.dirname(os.path.dirname(PYCLIF))
if "CLIF_DIR" not in os.environ:
    print("CLIF_DIR environment variable is not set.")
    print("Defaulting to {}".format(CLIF_DIR))
else:
    CLIF_DIR = os.environ['CLIF_DIR']

import numpy as np
NUMPY_INC_DIR = np.get_include()

if DEBUG:
    print("#"*50)
    print("CWD: {}".format(CWD))
    print("PYCLIF: {}".format(PYCLIF))
    print("KALDI_DIR: {}".format(KALDI_DIR))
    print("CLIF_DIR: {}".format(CLIF_DIR))
    print("CXX_FLAGS: {}".format(os.getenv("CXX_FLAGS")))
    print("#"*50)

################################################################################
# Workaround setuptools -Wstrict-prototypes warnings
# From: https://github.com/pytorch/pytorch/blob/master/setup.py
################################################################################
import distutils.sysconfig
cfg_vars = distutils.sysconfig.get_config_vars()
for key, value in cfg_vars.items():
    if type(value) == str:
        cfg_vars[key] = value.replace("-Wstrict-prototypes", "")

################################################################################
# Custom build commands
################################################################################
class build_deps(Command):
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        build_all_cmd = ['bash', 'build_all.sh', KALDI_DIR, PYCLIF, CLIF_DIR]
        if subprocess.call(build_all_cmd) != 0:
            sys.exit(1)


class build_ext(setuptools.command.build_ext.build_ext):
    def run(self):
        self.run_command("build_deps")
        return setuptools.command.build_ext.build_ext.run(self)

    def get_ext_filename(self, fullname):
        """Convert the name of an extension (eg. "foo.bar") into the name
        of the file from which it will be loaded (eg. "foo/bar.so"). This
        patch overrides platform specific extension suffix with ".so".
        """
        from distutils.sysconfig import get_config_var
        ext_path = fullname.split('.')
        ext_suffix = '.so'
        return os.path.join(*ext_path) + ext_suffix


class build(distutils.command.build.build):
    def finalize_options(self):
        self.build_base = 'build'
        self.build_lib = 'build/lib'
        distutils.command.build.build.finalize_options(self)

################################################################################
# Configure compile flags
################################################################################
library_dirs = ['build/lib/kaldi', KALDI_LIB_DIR]

runtime_library_dirs = ['$ORIGIN/..', '$ORIGIN', KALDI_LIB_DIR]

include_dirs = [
    CWD,
    os.path.join(CWD, 'build/kaldi'),  # Path to wrappers generated by clif
    os.path.join(CWD, 'kaldi'),  # Path to hand written wrappers
    os.path.join(CLIF_DIR, '..'),  # Path to clif install dir
    KALDI_SRC_DIR,
    os.path.join(KALDI_DIR, 'tools/openfst/include'),
    os.path.join(KALDI_DIR, 'tools/ATLAS/include'),
    NUMPY_INC_DIR,
]

extra_compile_args = [
    '-std=c++11',
    '-Wno-write-strings',
    '-DKALDI_DOUBLEPRECISION=0',
    '-DHAVE_EXECINFO_H=1',
    '-DHAVE_CXXABI_H',
    '-DHAVE_ATLAS',
    '-DKALDI_PARANOID'
]

extra_link_args = []

libraries = [':_clif.so']

if DEBUG:
    extra_compile_args += ['-O0', '-g', '-UNDEBUG']
    extra_link_args += ['-O0', '-g']

################################################################################
# Declare extensions and packages
################################################################################
extensions = []

clif = Extension(
    "kaldi._clif",
    sources=[
        os.path.join(CLIF_DIR, 'python/runtime.cc'),
        os.path.join(CLIF_DIR, 'python/slots.cc'),
        os.path.join(CLIF_DIR, 'python/types.cc'),
        ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs)
extensions.append(clif)

matrix_common = Extension(
    "kaldi.matrix.matrix_common",
    sources=[
        'build/kaldi/matrix/matrix-common-clifwrap.cc',
        'build/kaldi/matrix/matrix-common-clifwrap-init.cc',
        ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs,
    runtime_library_dirs=runtime_library_dirs,
    libraries=['kaldi-matrix', 'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(matrix_common)

kaldi_vector = Extension(
    "kaldi.matrix.kaldi_vector",
    sources=[
        'build/kaldi/matrix/kaldi-vector-clifwrap.cc',
        'build/kaldi/matrix/kaldi-vector-clifwrap-init.cc',
        ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':matrix_common.so', 'kaldi-matrix', 'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(kaldi_vector)

kaldi_matrix = Extension(
    "kaldi.matrix.kaldi_matrix",
    sources=[
        'build/kaldi/matrix/kaldi-matrix-clifwrap.cc',
        'build/kaldi/matrix/kaldi-matrix-clifwrap-init.cc',
    ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':kaldi_vector.so', ':matrix_common.so', 'kaldi-matrix',
               'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(kaldi_matrix)

kaldi_matrix_ext = Extension(
    "kaldi.matrix.kaldi_matrix_ext",
    sources=[
        'kaldi/matrix/kaldi-matrix-ext.cc',
        ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':kaldi_matrix.so', ':kaldi_vector.so', ':matrix_common.so',
               'kaldi-matrix', 'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(kaldi_matrix_ext)

matrix_functions = Extension(
    "kaldi.matrix.matrix_functions",
    sources = [
        "build/kaldi/matrix/matrix-functions-clifwrap.cc",
        "build/kaldi/matrix/matrix-functions-clifwrap-init.cc",
    ],
    language="c++",
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':kaldi_matrix.so', ':kaldi_vector.so', ':matrix_common.so',
               'kaldi-matrix', 'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(matrix_functions)

kaldi_io = Extension(
    "kaldi.util.kaldi_io",
    sources = [
        "build/kaldi/util/kaldi-io-clifwrap.cc",
        "build/kaldi/util/kaldi-io-clifwrap-init.cc"
    ],
    language = "c++",
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':kaldi_matrix.so', ':kaldi_vector.so', ':matrix_common.so',
               'kaldi-util', 'kaldi-matrix', 'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(kaldi_io)

kaldi_holder = Extension(
    "kaldi.util.kaldi_holder",
    sources = [
        "build/kaldi/util/kaldi-holder-clifwrap.cc",
        "build/kaldi/util/kaldi-holder-clifwrap-init.cc"
    ],
    language = "c++",
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix', 'build/lib/kaldi/util'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':kaldi_io.so', ':kaldi_matrix.so', ':kaldi_vector.so', ':matrix_common.so',
               'kaldi-util', 'kaldi-matrix', 'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(kaldi_holder)

# kaldi_table = Extension(
#     "kaldi.util.kaldi_table",
#     sources = [
#         "build/kaldi/util/kaldi-table-clifwrap.cc",
#         "build/kaldi/util/kaldi-table-clifwrap-init.cc"
#     ],
#     language = "c++",
#     extra_compile_args=extra_compile_args,
#     include_dirs=include_dirs,
#     library_dirs=library_dirs + ['build/lib/kaldi/matrix', 'build/lib/kaldi/util'],
#     runtime_library_dirs=runtime_library_dirs,
#     libraries=[':kaldi_holder.so', ':kaldi_io.so', ':kaldi_matrix.so', ':kaldi_vector.so', ':matrix_common.so',
#                'kaldi-util', 'kaldi-matrix', 'kaldi-base'] + libraries,
#     extra_link_args=extra_link_args)
# extensions.append(kaldi_table)

packages = find_packages()

setup(name = 'pykaldi',
      version = '0.0.1',
      description='Kaldi Python Wrapper',
      author='SAIL',
      ext_modules=extensions,
      cmdclass= {
          'build_deps': build_deps,
          'build_ext': build_ext,
          'build': build,
          },
      packages=packages,
      package_data={},
      install_requires=['enum34;python_version<"3.4"', 'numpy'])

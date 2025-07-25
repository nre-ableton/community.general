#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2021, Alexei Znamensky <russoz@gmail.com>
#
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r"""
module: ansible_galaxy_install
author:
  - "Alexei Znamensky (@russoz)"
short_description: Install Ansible roles or collections using ansible-galaxy
version_added: 3.5.0
description:
  - This module allows the installation of Ansible collections or roles using C(ansible-galaxy).
notes:
  - Support for B(Ansible 2.9/2.10) was removed in community.general 8.0.0.
  - The module tries to run using the C(C.UTF-8) locale. If that fails, it tries C(en_US.UTF-8). If that one also fails, the
    module fails.
seealso:
  - name: C(ansible-galaxy) command manual page
    description: Manual page for the command.
    link: https://docs.ansible.com/ansible/latest/cli/ansible-galaxy.html

requirements:
  - ansible-core 2.11 or newer
extends_documentation_fragment:
  - community.general.attributes
attributes:
  check_mode:
    support: none
  diff_mode:
    support: none
options:
  state:
    description:
      - If O(state=present) then the collection or role is installed. Note that the collections and roles are not updated
        with this option.
      - Currently the O(state=latest) is ignored unless O(type=collection), and it ensures the collection is installed and
        updated to the latest available version.
      - Please note that O(force=true) can be used to perform upgrade regardless of O(type).
    type: str
    choices: [present, latest]
    default: present
    version_added: 9.1.0
  type:
    description:
      - The type of installation performed by C(ansible-galaxy).
      - If O(type=both), then O(requirements_file) must be passed and it may contain both roles and collections.
      - 'Note however that the opposite is not true: if using a O(requirements_file), then O(type) can be any of the three
        choices.'
    type: str
    choices: [collection, role, both]
    required: true
  name:
    description:
      - Name of the collection or role being installed.
      - Versions can be specified with C(ansible-galaxy) usual formats. For example, the collection V(community.docker:1.6.1)
        or the role V(ansistrano.deploy,3.8.0).
      - O(name) and O(requirements_file) are mutually exclusive.
    type: str
  requirements_file:
    description:
      - Path to a file containing a list of requirements to be installed.
      - It works for O(type) equals to V(collection) and V(role).
      - O(name) and O(requirements_file) are mutually exclusive.
    type: path
  dest:
    description:
      - The path to the directory containing your collections or roles, according to the value of O(type).
      - Please notice that C(ansible-galaxy) does not install collections with O(type=both), when O(requirements_file) contains
        both roles and collections and O(dest) is specified.
    type: path
  no_deps:
    description:
      - Refrain from installing dependencies.
    version_added: 4.5.0
    type: bool
    default: false
  force:
    description:
      - Force overwriting existing roles and/or collections.
      - It can be used for upgrading, but the module output always reports C(changed=true).
      - Using O(force=true) is mandatory when downgrading.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: Install collection community.network
  community.general.ansible_galaxy_install:
    type: collection
    name: community.network

- name: Install role at specific path
  community.general.ansible_galaxy_install:
    type: role
    name: ansistrano.deploy
    dest: /ansible/roles

- name: Install collections and roles together
  community.general.ansible_galaxy_install:
    type: both
    requirements_file: requirements.yml

- name: Force-install collection community.network at specific version
  community.general.ansible_galaxy_install:
    type: collection
    name: community.network:3.0.2
    force: true
"""

RETURN = r"""
type:
  description: The value of the O(type) parameter.
  type: str
  returned: always
name:
  description: The value of the O(name) parameter.
  type: str
  returned: always
dest:
  description: The value of the O(dest) parameter.
  type: str
  returned: always
requirements_file:
  description: The value of the O(requirements_file) parameter.
  type: str
  returned: always
force:
  description: The value of the O(force) parameter.
  type: bool
  returned: always
installed_roles:
  description:
    - If O(requirements_file) is specified instead, returns dictionary with all the roles installed per path.
    - If O(name) is specified, returns that role name and the version installed per path.
  type: dict
  returned: always when installing roles
  contains:
    "<path>":
      description: Roles and versions for that path.
      type: dict
  sample:
    /home/user42/.ansible/roles:
      ansistrano.deploy: 3.9.0
      baztian.xfce: v0.0.3
    /custom/ansible/roles:
      ansistrano.deploy: 3.8.0
installed_collections:
  description:
    - If O(requirements_file) is specified instead, returns dictionary with all the collections installed per path.
    - If O(name) is specified, returns that collection name and the version installed per path.
  type: dict
  returned: always when installing collections
  contains:
    "<path>":
      description: Collections and versions for that path.
      type: dict
  sample:
    /home/az/.ansible/collections/ansible_collections:
      community.docker: 1.6.0
      community.general: 3.0.2
    /custom/ansible/ansible_collections:
      community.general: 3.1.0
new_collections:
  description: New collections installed by this module.
  returned: success
  type: dict
  sample:
    community.general: 3.1.0
    community.docker: 1.6.1
new_roles:
  description: New roles installed by this module.
  returned: success
  type: dict
  sample:
    ansistrano.deploy: 3.8.0
    baztian.xfce: v0.0.3
version:
  description: Version of ansible-core for ansible-galaxy.
  type: str
  returned: always
  sample: 2.17.4
  version_added: 10.0.0
"""

import re

from ansible_collections.community.general.plugins.module_utils.cmd_runner import CmdRunner, cmd_runner_fmt
from ansible_collections.community.general.plugins.module_utils.module_helper import ModuleHelper, ModuleHelperException


class AnsibleGalaxyInstall(ModuleHelper):
    _RE_GALAXY_VERSION = re.compile(r'^ansible-galaxy(?: \[core)? (?P<version>\d+\.\d+\.\d+)(?:\.\w+)?(?:\])?')
    _RE_LIST_PATH = re.compile(r'^# (?P<path>.*)$')
    _RE_LIST_COLL = re.compile(r'^(?P<elem>\w+\.\w+)\s+(?P<version>[\d\.]+)\s*$')
    _RE_LIST_ROLE = re.compile(r'^- (?P<elem>\w+\.\w+),\s+(?P<version>[\d\.]+)\s*$')
    _RE_INSTALL_OUTPUT = re.compile(
        r'^(?:(?P<collection>\w+\.\w+):(?P<cversion>[\d\.]+)|- (?P<role>\w+\.\w+) \((?P<rversion>[\d\.]+)\)) was installed successfully$'
    )
    ansible_version = None

    output_params = ('type', 'name', 'dest', 'requirements_file', 'force', 'no_deps')
    module = dict(
        argument_spec=dict(
            state=dict(type='str', choices=['present', 'latest'], default='present'),
            type=dict(type='str', choices=('collection', 'role', 'both'), required=True),
            name=dict(type='str'),
            requirements_file=dict(type='path'),
            dest=dict(type='path'),
            force=dict(type='bool', default=False),
            no_deps=dict(type='bool', default=False),
        ),
        mutually_exclusive=[('name', 'requirements_file')],
        required_one_of=[('name', 'requirements_file')],
        required_if=[('type', 'both', ['requirements_file'])],
        supports_check_mode=False,
    )

    command = 'ansible-galaxy'
    command_args_formats = dict(
        type=cmd_runner_fmt.as_func(lambda v: [] if v == 'both' else [v]),
        galaxy_cmd=cmd_runner_fmt.as_list(),
        upgrade=cmd_runner_fmt.as_bool("--upgrade"),
        requirements_file=cmd_runner_fmt.as_opt_val('-r'),
        dest=cmd_runner_fmt.as_opt_val('-p'),
        force=cmd_runner_fmt.as_bool("--force"),
        no_deps=cmd_runner_fmt.as_bool("--no-deps"),
        version=cmd_runner_fmt.as_fixed("--version"),
        name=cmd_runner_fmt.as_list(),
    )

    def _make_runner(self, lang):
        return CmdRunner(self.module, command=self.command, arg_formats=self.command_args_formats, force_lang=lang, check_rc=True)

    def _get_ansible_galaxy_version(self):
        class UnsupportedLocale(ModuleHelperException):
            pass

        def process(rc, out, err):
            if (rc != 0 and "unsupported locale setting" in err) or (rc == 0 and "cannot change locale" in err):
                raise UnsupportedLocale(msg=err)
            line = out.splitlines()[0]
            match = self._RE_GALAXY_VERSION.match(line)
            if not match:
                self.do_raise("Unable to determine ansible-galaxy version from: {0}".format(line))
            version = match.group("version")
            return version

        try:
            runner = self._make_runner("C.UTF-8")
            with runner("version", check_rc=False, output_process=process) as ctx:
                return runner, ctx.run()
        except UnsupportedLocale:
            runner = self._make_runner("en_US.UTF-8")
            with runner("version", check_rc=True, output_process=process) as ctx:
                return runner, ctx.run()

    def __init_module__(self):
        self.runner, self.vars.version = self._get_ansible_galaxy_version()
        self.ansible_version = tuple(int(x) for x in self.vars.version.split('.')[:3])
        if self.ansible_version < (2, 11):
            self.module.fail_json(msg="Support for Ansible 2.9 and ansible-base 2.10 has been removed.")
        self.vars.set("new_collections", {}, change=True)
        self.vars.set("new_roles", {}, change=True)
        if self.vars.type != "collection":
            self.vars.installed_roles = self._list_roles()
        if self.vars.type != "roles":
            self.vars.installed_collections = self._list_collections()

    def _list_element(self, _type, path_re, elem_re):
        def process(rc, out, err):
            return [] if "None of the provided paths were usable" in out else out.splitlines()

        with self.runner('type galaxy_cmd dest', output_process=process, check_rc=False) as ctx:
            elems = ctx.run(type=_type, galaxy_cmd='list')

        elems_dict = {}
        current_path = None
        for line in elems:
            if line.startswith("#"):
                match = path_re.match(line)
                if not match:
                    continue
                if self.vars.dest is not None and match.group('path') != self.vars.dest:
                    current_path = None
                    continue
                current_path = match.group('path') if match else None
                elems_dict[current_path] = {}

            elif current_path is not None:
                match = elem_re.match(line)
                if not match or (self.vars.name is not None and match.group('elem') != self.vars.name):
                    continue
                elems_dict[current_path][match.group('elem')] = match.group('version')
        return elems_dict

    def _list_collections(self):
        return self._list_element('collection', self._RE_LIST_PATH, self._RE_LIST_COLL)

    def _list_roles(self):
        return self._list_element('role', self._RE_LIST_PATH, self._RE_LIST_ROLE)

    def __run__(self):

        def process(rc, out, err):
            for line in out.splitlines():
                match = self._RE_INSTALL_OUTPUT.match(line)
                if not match:
                    continue
                if match.group("collection"):
                    self.vars.new_collections[match.group("collection")] = match.group("cversion")
                elif match.group("role"):
                    self.vars.new_roles[match.group("role")] = match.group("rversion")

        upgrade = (self.vars.type == "collection" and self.vars.state == "latest")
        with self.runner("type galaxy_cmd upgrade force no_deps dest requirements_file name", output_process=process) as ctx:
            ctx.run(galaxy_cmd="install", upgrade=upgrade)
            if self.verbosity > 2:
                self.vars.set("run_info", ctx.run_info)


def main():
    AnsibleGalaxyInstall.execute()


if __name__ == '__main__':
    main()

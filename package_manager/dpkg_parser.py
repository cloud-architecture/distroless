# Copyright 2017 Google Inc. All rights reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import gzip
import urllib2
import json
import os


from package_manager.parse_metadata import parse_package_metadata
from package_manager import util

OUT_FOLDER = "file"
PACKAGES_FILE_NAME = os.path.join(OUT_FOLDER,"Packages.json")
PACKAGE_MAP_FILE_NAME = os.path.join(OUT_FOLDER,"packages.bzl")
DEB_FILE_NAME = os.path.join(OUT_FOLDER,"pkg.deb")

FILENAME_KEY = "Filename"
SHA256_KEY = "SHA256"
VERSION_KEY = "Version"

parser = argparse.ArgumentParser(
    description="Downloads a deb package from a package source file"
)

parser.add_argument("--package-files", action='store',
                    help='A list of Packages.gz files to use')
parser.add_argument("--packages", action='store',
                    help='A comma delimited list of packages to search for and download')
parser.add_argument("--workspace-name", action='store',
                    help='The name of the current bazel workspace')

parser.add_argument("--download-and-extract-only", action='store',
                    help='If True, download Packages.gz and make urls absolute from mirror url')
parser.add_argument("--mirror-url", action='store',
                    help='The base url for the package list mirror')
parser.add_argument("--arch", action='store',
                    help='The target architecture for the package list')
parser.add_argument("--distro", action='store',
                    help='The target distribution for the package list')
parser.add_argument("--snapshot", action='store',
                    help='The snapshot date to download')
parser.add_argument("--sha256", action='store',
                    help='The sha256 checksum to validate for the Packages.gz file')

def main():
    """ A tool for downloading debian packages and package metadata """
    args = parser.parse_args()
    if args.download_and_extract_only:
        download_package_list(args.mirror_url, args.distro, args.arch, args.snapshot, args.sha256)
    else:
        download_dpkg(args.package_files, args.packages, args.workspace_name)


def download_dpkg(package_files, packages, workspace_name):
    """ Using an unzipped, json package file with full urls,
     downloads a .deb package

    Uses the 'Filename' key to download the .deb package
    """
    pkg_vals_to_package_file_and_sha256 = {}
    package_to_rule_map = {}
    for pkg_vals in packages.split(","):
        pkg_split = pkg_vals.split("=")
        if len(pkg_split) != 2:
            pkg_name = pkg_vals
            pkg_version = ""
        else:
            pkg_name, pkg_version = pkg_split
        for package_file in package_files.split(","):
            with open(package_file, 'rb') as f:
                metadata = json.load(f)
            if (pkg_name in metadata and 
            (pkg_version == "" or
            pkg_version == metadata[pkg_name][VERSION_KEY])):
                pkg = metadata[pkg_name]
                buf = urllib2.urlopen(pkg[FILENAME_KEY])
                package_to_rule_map[pkg_name] = util.package_to_rule(workspace_name, pkg_name)
                out_file = os.path.join("file", util.encode_package_name(pkg_name))
                with open(out_file, 'w') as f:
                    f.write(buf.read())
                expected_checksum = util.sha256_checksum(out_file)
                actual_checksum = pkg[SHA256_KEY]
                if actual_checksum != expected_checksum:
                    raise Exception("Wrong checksum for package %s.  Expected: %s, Actual: %s", pkg_name, expected_checksum, actual_checksum)
                if pkg_version == "":
                    break
                if (pkg_vals in pkg_vals_to_package_file_and_sha256 and 
                pkg_vals_to_package_file_and_sha256[pkg_vals][1] != actual_checksum):
                    raise Exception("Conflicting checksums for package %s, version %s.  Conflicting checksums: %s:%s, %s:%s", 
                    pkg_name, pkg_version, 
                    pkg_vals_to_package_file_and_sha256[pkg_vals][0], pkg_vals_to_package_file_and_sha256[pkg_vals][1],
                    package_file, actual_checksum)
                else:
                    pkg_vals_to_package_file_and_sha256[pkg_vals] = [package_file, actual_checksum]
                break
        else:
            raise Exception("Package: %s, Version: %s not found in any of the sources" % (pkg_name, pkg_version))
    with open(PACKAGE_MAP_FILE_NAME, 'w') as f:
        f.write("packages = " + json.dumps(package_to_rule_map))

def download_package_list(mirror_url, distro, arch, snapshot, sha256):
    """Downloads a debian package list, expands the relative urls,
    and saves the metadata as a json file

    A debian package list is a gzipped, newline delimited, colon separated
    file with metadata about all the packages available in that repository.
    Multiline keys are indented with spaces.

    An example package looks like:

Package: newmail
Version: 0.5-2
Installed-Size: 76
Maintainer: Martin Schulze <joey@debian.org>
Architecture: amd64
Depends: libc6 (>= 2.7-1)
Description: Notificator for incoming mail
Homepage: http://www.infodrom.org/projects/newmail/
Description-md5: 49b0168ce625e668ce3031036ad2f541
Tag: interface::commandline, mail::notification, role::program,
 scope::utility, works-with::mail
Section: mail
Priority: optional
Filename: pool/main/n/newmail/newmail_0.5-2_amd64.deb
Size: 14154
MD5sum: 5cd31aab55877339145517fb6d5646cb
SHA1: 869934a25a8bb3def0f17fef9221bed2d3a460f9
SHA256: 52ec3ac93cf8ba038fbcefe1e78f26ca1d59356cdc95e60f987c3f52b3f5e7ef

    """
    url = "%s/debian/%s/dists/%s/main/binary-%s/Packages.gz" % (
        mirror_url,
        snapshot,
        distro,
        arch
    )
    buf = urllib2.urlopen(url)
    with open("Packages.gz", 'w') as f:
        f.write(buf.read())
    actual_sha256 = util.sha256_checksum("Packages.gz")
    if sha256 != actual_sha256:
        raise Exception("sha256 of Packages.gz don't match: Expected: %s, Actual:%s" %(sha256, actual_sha256))
    with gzip.open("Packages.gz", 'rb') as f:
        data = f.read()
    metadata = parse_package_metadata(data, mirror_url, snapshot)
    with open(PACKAGES_FILE_NAME, 'w') as f:
        json.dump(metadata, f)

if __name__ == "__main__":
    main()


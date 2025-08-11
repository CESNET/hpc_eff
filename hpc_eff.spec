%define name hpc_eff
%define version 0.1
%define release 1

Name:           %{name}
Version:        %{version}
Release:        %{release}
Summary:        Energy Optimization Governor
License:        GPL-3.0-or-later
Group:          System Environment/Base
BuildArch:      noarch
Vendor:         CESNET
Source0:        %{name}-%{version}.tar.gz

Requires:       python3
Requires:       python3-numpy
Requires:       python3-requests
BuildRequires:  ipmitool
Requires:       ipmitool

# Disable .pyc/.pyo bytecode compilation during build
%define __brp_python_bytecompile %{nil}

%description
This tool dynamically optimizes energy consumption on HPC systems by
adjusting the CPU frequency according to the current carbon intensity (CI)
of electricity production.

Designed to be run periodically (e.g., via cron every 5 minutes under root),
it applies a hardcoded policy that limits CPU frequency in proportion to
real-time carbon intensity data obtained from the GreenDIGIT CI database.
The frequency regulator outputs a standardized score (0–100), representing
the percentage limit relative to the maximum CPU frequency.

%prep
%setup -q -n %{name}-%{version}

%build
python3 setup.py build

%install
python3 setup.py install --root=%{buildroot} --prefix=/usr --skip-build --record=INSTALLED_FILES
install -D -m 644 src/hpc_eff/config.ini.example %{buildroot}/etc/hpc_eff/config.ini

%files -f INSTALLED_FILES
%defattr(-,root,root,-)
%config(noreplace) /etc/hpc_eff/config.ini
%doc README.md

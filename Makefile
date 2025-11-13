NAME = hpc_eff
VERSION = 0.1
RELEASE = 1
RPMDIR = $(HOME)/rpmbuild
TARBALL = dist/$(NAME)-$(VERSION).tar.gz
SPECFILE = $(RPMDIR)/SPECS/$(NAME).spec
RPMFILE = $(RPMDIR)/RPMS/noarch/$(NAME)-$(VERSION)-1.noarch.rpm

.PHONY: all clean sdist rpm install reinstall rpmdevdirs

all: build

build: clean rpmdevdirs sdist rpm install

clean:
	rm -rf build/ dist/ src/$(NAME).egg-info/
	rm -rf $(RPMDIR)/BUILD/$(NAME)-$(VERSION)
	rm -rf $(RPMDIR)/BUILDROOT/$(NAME)-$(VERSION)-1.x86_64
	rm -f $(RPMFILE)

rpmdevdirs:
	@mkdir -p $(RPMDIR)/{BUILD,RPMS,SOURCES,SPECS,SRPMS,BUILDROOT}
	cp hpc_eff.spec $(RPMDIR)/SPECS/

sdist:
	python3 setup.py sdist
	cp $(TARBALL) $(RPMDIR)/SOURCES/

rpm:
	rpmbuild -ba $(SPECFILE) \
	    --define "version $(VERSION)" \
	    --define "release $(RELEASE)"

install:
	sudo dnf install -y $(RPMFILE)

reinstall:
	sudo rpm -Uvh --replacepkgs $(RPMFILE)

uninstall:
	sudo rpm -e $(NAME)

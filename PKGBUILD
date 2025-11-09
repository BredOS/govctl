# Maintainer: Bill Sideris <bill88t@bredos.org>

pkgname=bredos-govctl
pkgver=1.3.1
pkgrel=1
pkgdesc="BredOS CPU/devfreq governor manager"

arch=('any')
url="https://BredOS.org/"
license=('GPL3')

groups=(bredos)
depends=('python' 'systemd' 'python-bredos-common')
optdepends=('ryzenadj: Configuring TDP on AMD systems')

backup=('etc/govctl/config.json')
source=('govctl_service.py'
        'govctl_cli.py'
        'govctl.service'
        'default_config.json'
        'govctl.8'
        'raplctl.py')

sha256sums=('19df0b8c7a4f7a4ba89f268d7d7b416f95864ccca68a1d5a9abd977e1cea5d31'
            'b93529acded3af791fec1a28cc1f71af91b411bdf9fd988e7fb881cf30175dc4'
            '4cdf3822953fbc9fb9dc7048060f06c4817cf905d51c2e087068184a7a5bfc92'
            '3e627d45c261167b466a1d8d389d26de83935ad99cb51050361ca8cbb33a2c4a'
            'e8ea1f038dfeaf86e8008a61d05cd4ba0a7ca33c3a7c71894749b0330b4c2364'
            '4d25257b599e9be37106df5482e24715ff715f23905363fb22600f2ddee90945')

install=govctl.install

package() {
    # Govctl
    install -Dm755 govctl_service.py "${pkgdir}/usr/bin/govctl_service"
    install -Dm755 govctl_cli.py "${pkgdir}/usr/bin/govctl"

    # Intel RAPL
    install -Dm755 raplctl.py "${pkgdir}/usr/bin/raplctl"

    # Services
    install -Dm644 govctl.service "${pkgdir}/usr/lib/systemd/system/govctl.service"

    # Default config
    install -d "${pkgdir}/etc/govctl/"
    install -Dm644 default_config.json "${pkgdir}/etc/govctl/config.json"

    # Install man pages
    install -Dm644 govctl.8 "${pkgdir}/usr/share/man/man8/govctl.8"
}

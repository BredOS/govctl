# Maintainer: Bill Sideris <bill88t@bredos.org>

pkgname=bredos-govctl
pkgver=1.1.0
pkgrel=1
pkgdesc="BredOS CPU/devfreq governor manager."

arch=('any')
url="https://BredOS.org/"

license=('GPL3')
depends=('python' 'systemd')

backup=('etc/govctl/config.json')
source=('govctl_service.py'
        'govctl_cli.py'
        'govctl.service'
        'default_config.json')

sha256sums=('SKIP'
            'SKIP'
            'SKIP'
            'SKIP')

install=govctl.install

package() {
    install -Dm755 govctl_service.py "${pkgdir}/usr/bin/govctl_service.py"
    install -Dm755 govctl_cli.py "${pkgdir}/usr/bin/govctl"

    install -Dm644 govctl.service "${pkgdir}/usr/lib/systemd/system/govctl.service"

    install -d "${pkgdir}/etc/govctl/"
    install -Dm644 default_config.json "${pkgdir}/etc/govctl/config.json"
}

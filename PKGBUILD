# Maintainer: Bill Sideris <bill88t@bredos.org>

pkgname=bredos-govctl
pkgver=1.3.0
pkgrel=1
pkgdesc="BredOS CPU/devfreq governor manager"

arch=('any')
url="https://BredOS.org/"
license=('GPL3')

groups=(bredos)
depends=('python' 'systemd' 'python-bredos-common')

backup=('etc/govctl/config.json')
source=('govctl_service.py'
        'govctl_cli.py'
        'govctl.service'
        'default_config.json'
        'govctl.8'
        'raplctl.py')

sha256sums=('1eb7aca3374f1f598df2f2e668cbc2aef8855ca6a213afd3fcd8e481ed8dda21'
            '210a8d93792f82fd642976bc861c62c7711bef35bb5785a39658e9a3ab54a828'
            '4cdf3822953fbc9fb9dc7048060f06c4817cf905d51c2e087068184a7a5bfc92'
            'ff1a6d645148ed5dccf7a7f85ed577f9d2bcac36a094e6a5570dcdce0d4d5c18'
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

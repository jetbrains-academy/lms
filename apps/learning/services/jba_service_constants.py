# From https://code.jetbrains.team/p/tbx/repositories/ultimate/files/ce4332bbcf90275380623851db2d6f5b88c9a3ab/toolbox/feed/src/feeds/bundled-linux.feed
# https://code.jetbrains.team/p/mp/repositories/marketplace/files/649deba5ace515822a43692e5fc0582dc09917a4/ui/entities/plugins/types.ts
# https://code.jetbrains.team/p/mp/repositories/marketplace/files/649deba5ace515822a43692e5fc0582dc09917a4/ui/pages/dashboard/dashboard.util.ts
from enum import Enum


class ProgrammingLanguage(str, Enum):
    PYTHON = 'Python'
    RUST = 'Rust'
    GO = 'go'
    OBJECTIVE_C = 'ObjectiveC'
    JAVA_SCRIPT = 'JavaScript'
    KOTLIN = 'kotlin'
    SCALA = 'Scala'
    JAVA = 'JAVA'
    PHP = 'PHP'

    # TODO: python 3.12+ supports `value in Enum` syntax
    @classmethod
    def contains(cls, value):
        return value in cls._value2member_map_


class JBProduct(str, Enum):
    IDEA = 'IDEA-U'
    IDEA_COMMUNITY = 'IDEA-C'
    PHPSTORM = 'PhpStorm'
    WEBSTORM = 'WebStorm'
    PYCHARM = 'PyCharm-U'
    PYCHARM_COMMUNITY = 'PyCharm-C'
    RUBYMINE = 'RubyMine'
    CLION = 'CLion'
    GOLAND = 'Goland'
    RIDER = 'Rider'
    RUST = 'RustRover'


IDE_BY_LANGUAGE = {
    ProgrammingLanguage.PYTHON: [
        JBProduct.PYCHARM_COMMUNITY,
        JBProduct.PYCHARM,
        JBProduct.IDEA,
        JBProduct.IDEA_COMMUNITY,
    ],
    ProgrammingLanguage.RUST: [
        JBProduct.RUST,
        JBProduct.CLION,
        JBProduct.IDEA,
        JBProduct.GOLAND,
        JBProduct.IDEA_COMMUNITY,
        JBProduct.PYCHARM_COMMUNITY,
        JBProduct.PYCHARM,
        JBProduct.WEBSTORM,
    ],
    ProgrammingLanguage.GO: [JBProduct.GOLAND],
    ProgrammingLanguage.JAVA_SCRIPT: [JBProduct.WEBSTORM, JBProduct.IDEA],
    ProgrammingLanguage.KOTLIN: [JBProduct.IDEA_COMMUNITY, JBProduct.IDEA],
    ProgrammingLanguage.SCALA: [JBProduct.IDEA_COMMUNITY, JBProduct.IDEA],
    ProgrammingLanguage.JAVA: [JBProduct.IDEA_COMMUNITY, JBProduct.IDEA],
    ProgrammingLanguage.PHP: [JBProduct.IDEA, JBProduct.PHPSTORM, JBProduct.WEBSTORM],
}

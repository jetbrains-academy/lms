import pytest

from core.models import City, AcademicProgram, AcademicProgramRun, University
from core.tests.factories import AcademicProgramRunFactory


@pytest.fixture()
@pytest.mark.django_db
def university_cub():
    bremen = City()
    bremen.code = 'BRE'
    bremen.name = 'Bremen'
    bremen.abbr = 'Bremen'
    bremen.time_zone = 'Europe/Berlin'
    bremen.save()

    cub = University()
    cub.name = 'Constructor University Bremen'
    cub.abbr = 'CUB'
    cub.city = bremen
    cub.save()

    return cub


@pytest.fixture()
@pytest.mark.django_db
def university_nup():
    paphos = City()
    paphos.code = 'PFO'
    paphos.abbr = 'Pafos'
    paphos.name = 'Pafos'
    paphos.time_zone = 'Asia/Nicosia'
    paphos.save()

    nup = University()
    nup.name = 'Neapolis University Pafos'
    nup.abbr = 'NUP'
    nup.city = paphos
    nup.save()

    return nup


@pytest.fixture()
@pytest.mark.django_db
def program_cub001(university_cub):
    cub001 = AcademicProgram()
    cub001.title = 'Software, Data and Technology'
    cub001.code = 'CUB-001'
    cub001.university = university_cub
    cub001.save()
    return cub001


@pytest.fixture()
@pytest.mark.django_db
def program_nup001(university_nup):
    cub001 = AcademicProgram()
    cub001.title = 'Computer Science and Artificial Intelligence'
    cub001.code = 'NUP-001'
    cub001.university = university_nup
    cub001.save()
    return cub001


@pytest.fixture()
@pytest.mark.django_db
def program_run_cub(program_cub001):
    return AcademicProgramRunFactory(program=program_cub001)


@pytest.fixture()
@pytest.mark.django_db
def program_run_nup(program_nup001):
    return AcademicProgramRunFactory(program=program_nup001)

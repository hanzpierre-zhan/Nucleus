"""Selección de citas de ciencia y tecnología para Inicio."""
from datetime import date

FECHA_INICIAL = date(2026, 11, 20)
CITAS = (
    ('Si aún no lo has encontrado, sigue buscando. No te conformes.', 'Steve Jobs', 'https://news.stanford.edu/stories/2005/06/youve-got-find-love-jobs-says'),
    ('Disfruta lo que haces y darás lo mejor de ti.', 'Katherine Johnson', 'https://science.nasa.gov/people/katherine-johnson/'),
    ('No puedes ser lo que no puedes ver.', 'Sally Ride', 'https://www.nasa.gov/humans-in-space/legacy-lives-on-for-sally-ride-nasas-first-woman-in-space/'),
    ('La prueba de todo conocimiento es el experimento.', 'Richard Feynman', 'https://www.feynmanlectures.caltech.edu/FLP_Lecture_1_Transcript.pdf'),
    ('Siempre busqué la manera más fácil, mejor y más precisa de hacer las cosas.', 'Grace Hopper', 'https://archive.computerhistory.org/resources/text/Oral_History/Hopper_Grace/102702026.05.01.pdf'),
    ('Haz siempre lo mejor que puedas, porque eso contará.', 'Richard Mullane', 'https://www.nasa.gov/wp-content/uploads/2025/08/mullanerm-1-24-03.pdf'),
    ('El primer principio es que no debes engañarte a ti mismo.', 'Richard Feynman', 'https://calteches.library.caltech.edu/51/2/CargoCult.htm'),
    ('Escribimos nuestro propio libro de texto, porque no existía ninguno sobre el espacio.', 'Katherine Johnson', 'https://www.nasa.gov/wp-content/uploads/2024/01/ivv-meet-katherine-johnson-handout.pdf'),
    ('La única manera de hacer un gran trabajo es amar lo que haces.', 'Steve Jobs', 'https://news.stanford.edu/stories/2005/06/youve-got-find-love-jobs-says'),
    ('No sabes de lo que eres capaz hasta que te pones el listón muy alto.', 'Richard Mullane', 'https://www.nasa.gov/wp-content/uploads/2025/08/mullanerm-1-24-03.pdf'),
)


def frase_para(fecha):
    return CITAS[(FECHA_INICIAL - fecha).days % len(CITAS)]

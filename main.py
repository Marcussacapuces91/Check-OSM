import csv

import esy.osm.pbf
import datetime
import re
import logging


class Application:

    def __init__(self):
        self.names: dict
        self.errors: int

        self._keys = list()
        with open('deprecated_keys.csv', newline='') as f:
            reader = csv.reader(f)
            next(reader)  # Saute la 1ère ligne
            for row in reader:
                self._keys.append(row[0])
        self._tags = list()
        with open('deprecated_tags.csv', newline='') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                self._tags.append((row[0], row[1]))

    def _nwr(self, entry) -> str:
        return 'node' if type(entry) == esy.osm.pbf.file.Node else 'way' if type(
            entry) == esy.osm.pbf.file.Way else 'relation'

    def add_names(self, entry):
        """Compte les libellés de 'name' dans une liste les regroupant tous."""
        n = entry.tags['name']
        try:
            self.names[n].add(f'{self._nwr(entry)}/{entry.id}')
        except KeyError:
            self.names[n] = {f'{self._nwr(entry)}/{entry.id}'}

    def name_egale_addr_housenumber(self, entry):
        """Recherche name = addr:housenumber"""
        try:
            if entry.tags['name'] == entry.tags['addr:housenumber']:
                self.errors += 1
                log.warning(
                    f"name = addr:housenumber ({entry.tags['name']})",
                    extra={'type': self._nwr(entry), 'id': entry.id}
                )
        except KeyError:
            pass

    def name_egale_ref(self, entry):
        """Recherche name = addr:housenumber"""
        try:
            if entry.tags['name'] == entry.tags['ref']:
                self.errors += 1
                log.warning(
                    f"name = ref ({entry.tags['name']})",
                    extra={'type': self._nwr(entry), 'id': entry.id}
                )
        except KeyError:
            pass

    def name_commence_ou_termine_par_espace(self, entry):
        """name commence ou se termine par un espace"""
        if re.match(r'^\s', entry.tags['name']):
            self.errors += 1
            log.error(
                f"'name' commence par un espace ({entry.tags['name']})",
                extra={'type': self._nwr(entry), 'id': entry.id}
            )
        if re.match(r'\s$', entry.tags['name']):
            self.errors += 1
            log.info(
                "'name' se termine par un espace ({entry.tags['name']})",
                extra={'type': self._nwr(entry), 'id': entry.id}
            )

    def name_commence_par_un_chiffre(self, entry):
        """Name commence avec un chiffre sauf shops sauf ..."""
        mois = (
            'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
            'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
        )
        try:
            # si commence par un chiffre mais...
            # est un shop
            # est un amenity
            # est un numérique suivi d'un mois de l'année (date historique)
            # est 1er, 2ème etc.
            if re.match(r'^\d', entry.tags['name']) and \
                    'shop' not in entry.tags and \
                    'amenity' not in entry.tags and \
                    not re.match(f'^\d+ ({"|".join(mois)})', entry.tags['name']) and \
                    not re.match(r'^(1er|1ère|\d+e|\d+è)\s', entry.tags['name']):
                self.errors += 1
                log.warning(
                    f"'name' commence par un chiffre ({entry.tags['name']})",
                    extra={'type': self._nwr(entry), 'id': entry.id}
                )
        except KeyError:
            pass

    def tag_deprecie(self, entry):
        """Tags (key/value) dépréciés"""
        for k in entry.tags:
            if (k, entry.tags[k]) in self._tags:
                self.errors += 1
                log.info(
                    f"Tag \'{k}\'=\'{entry.tags[k]}\' déprécié ({entry.tags['name']})",
                    extra={'type': self._nwr(entry), 'id': entry.id}
                )

    def key_deprecie(self, entry):
        """Key dépréciés"""
        for k in entry.tags:
            if k in self._keys:
                self.errors += 1
                log.info(
                    f"Key \'{k}\' dépréciée ({entry.tags['name']})",
                    extra={'type': self._nwr(entry), 'id': entry.id}
                )

    def check_name(self, entry):
        """Vérifie le contenu du champ name et sa validité"""
        highway_black_list = (
            r'^Chemin Ancien Chemin ',
            r'^Chemin Chemin ',
            r'^Chemin [Rr]ural (No|Numéro|n°)',
            r'^Chemin Vicinal ',
            r'^\w+ [A-Z]+\.',   # Abréviation
            r'^\w+ Georges Sand',
            r'^\w+ Pierre Ronsard',
            r'^\w+ Roger-Martin du Gard',
            r'^\w+ Marroniers*',
            r'^\w+ D\'\w+',
            r'^\w+ De \w+',
            r'^\w+ Des \w+'
        )
        """Liste des noms de voies formellement erronnées."""

        highway_type_valid_list = (
            'Allée', 'Ancien Chemin', 'Autoroute', 'Avenue',
            'Basse Corniche', 'Belvédère', 'Boucle', 'Boulevard', 'Bretelle',
            'Carreau', 'Carrefour', 'Chasse', 'Chaussée', 'Chemin', 'Cité', 'Clos', 'Corniche', 'Cour', 'Cours', 'Côte',
            'Descente', 'Domaine',
            'Échangeur', 'Espace', 'Esplanade',
            'Faubourg',
            'Grand Place', 'Grande Route', "Grand'Rue", 'Grande Rue', 'Giratoire',
            'Hameau',
            'Impasse',
            'Jardins?',
            'Les Quatre Routes', 'Lotissement',
            'Mail', 'Montée',
            'Place', 'Parc', 'Parvis', 'Passage', 'Passerelle', 'Périphérique', 'Petite Rue', 'Pont', 'Port', 'Porte', 'Promenade',
            'Quai',
            'Résidence', 'Rocade', 'Rond-Point', 'Route', 'Rue',
            'Sente', 'Sentier', 'Square', 'Sortie',
            'Terrasse', 'Traverse', 'Tunnel',
            'Viaduc', 'Villa', 'Voie',

            "L'Aquitaine", 'La Francilienne', 'L’Océane', "L'Européenne", 'La Comtoise', 'La Provençale',
            'La Languedocienne', 'La Méridienne', "L'Arverne", 'La Transeuropéenne', "L'Occitane",
        )
        """Liste des 1ers nom de voie usuels"""
        highway_type_ignore_list = (
            # Allemagne
            'Am Altrheinhafen', 'Austraße',
            'Bachweg', 'Badener', 'Berger', 'Berliner',
            'Cabot',
            'Dammstraße', 'Dammweg', 'Darrweg',
            'Eichenweg', 'Elsässerstrasse'
            'Fischerstraße', 'Fliederweg', 'Friedhofstraße',
            'Greitweg', 'Grünfelderstraße',
            'Hafenstraße', 'Hans-Thoma-Straße', 'Hechtgasse', 'Hinterlanddamm',
            'Industriestraße', 'Im Grün', 'Im Rheinwald',
            'Glockenstraße', 'Grißheimer', 'Gustav-Regler-Platz',
            'Josefsgasse'
            'Kreuzstraße',
            'Lindenstraße',
            'Messeplatz', 'Mittelstraße',
            'Narzissenweg', 'Nelkenstraße', 'Neuburgweierer',
            'Oberwaldstraße',
            'Panoramaweg', 'Pappelweg', 'Pfalzstraße', 'Pfarrstraße',
            'Rathausplatz', 'Rheindamm', 'Rheinseitenstraße', 'Rheinstraße', 'Ringstraße', 'Robert-Bosch-Straße', 'Russenstraße',
            'Schifferweg', 'Schmiedgasse', 'Steinstraße', 'Südendstraße'
            'Tullastraße', 'Tulpenstraße',
            'Ulmer',
            'Victoria',
            'Wörthweg',
            'Zainweg', 'Zwiebelbühndstraße',

            # Monaco
            'Lacets Saint-Léon'
            'Rascasse',
            'Virage Antony Nogues',

        )
        """Liste des 1ers nom de voie non-testés (étrangers)."""

        highway_value_list = (
            'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified', 'residential',
            'motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link',
            'living_street', 'service', 'pedestrian', 'track', 'bus_guideway', 'road', 'busway'
        )
        """Types (tags) de voies auxquelles les tests de nommage s'appliquent."""

        try:
            if entry.tags['highway'] in highway_value_list:
                if re.match(f'^({"|".join(highway_type_valid_list)})', entry.tags['name']):
                    for regle in highway_black_list:
                        if re.match(regle, entry.tags['name']):
                            self.errors += 1
                            log.error(
                                f"Erreur/Typo sur nom de voie ({entry.tags['name']})",
                                extra={'type': self._nwr(entry), 'id': entry.id}
                            )
                else:
                    if not re.match(f'(^({"|".join(highway_type_ignore_list)}))', entry.tags['name']):
                        self.errors += 1
                        log.debug(
                            f"Type de voie inconnue ({entry.tags['name']})",
                            extra={'type': self._nwr(entry), 'id': entry.id}
                        )
        except KeyError:
            pass

    def parse_block(self, block_, nodes_: int, ways_: int, relations_: int) -> (int, int, int):
        for entry in block_:
            match type(entry):
                case esy.osm.pbf.file.Node:
                    nodes_ += 1
                    try:
                        self.add_names(entry)
                        self.check_name(entry)
                        self.name_egale_addr_housenumber(entry)
                        self.name_egale_ref(entry)
                        self.name_commence_ou_termine_par_espace(entry)
                        self.name_commence_par_un_chiffre(entry)
                    except KeyError:  # Pas de name
                        pass

                    # self.key_deprecie(entry)
                    # self.tag_deprecie(entry)

                case esy.osm.pbf.file.Way:
                    ways_ += 1
                    try:
                        self.add_names(entry)
                        self.check_name(entry)
                        self.name_egale_addr_housenumber(entry)
                        self.name_egale_ref(entry)
                        self.name_commence_ou_termine_par_espace(entry)
                        self.name_commence_par_un_chiffre(entry)
                    except KeyError:  # Pas de name
                        pass

                    # self.key_deprecie(entry)
                    # self.tag_deprecie(entry)

                case esy.osm.pbf.file.Relation:
                    relations_ += 1
                    try:
                        self.add_names(entry)
                        self.check_name(entry)
                        self.name_egale_ref(entry)
                        self.name_commence_ou_termine_par_espace(entry)
                    except KeyError:  # Pas de name
                        pass

                    # self.key_deprecie(entry)
                    # self.tag_deprecie(entry)

        return nodes_, ways_, relations_

    def parse(self, file: esy.osm.pbf.File):
        blocks = list(file.blocks)
        size = len(blocks)
        nodes, ways, relations = 0, 0, 0
        self.errors = 0

        self.names = {}
        start = datetime.datetime.now()
        for i, block in enumerate(blocks):
            nodes, ways, relations = self.parse_block(block, nodes, ways, relations)
            now = datetime.datetime.now()
            end = start + (now - start) / ((i + 1) / size)
            print(f'{now.strftime("%H:%M:%S")} ({(i + 1) / size:3.2%}) -> {end.strftime("%H:%M")} :',
                  f'Names : {len(self.names)}, Errors : {self.errors}',
                  f'- Nodes : {nodes:,} - Ways : {ways:,} - Rels : {relations:,}')


if __name__ == '__main__':
    FORMAT = '%(asctime)s [%(lineno)5d] %(levelname)8s - %(funcName)s - %(message)s ' \
             'https://www.openstreetmap.org/%(type)s/%(id)s'
    logging.basicConfig(filename='openstreetmap.log', filemode='w', encoding='utf-8', level=logging.DEBUG,
                        format=FORMAT)
    log = logging.getLogger()

    with esy.osm.pbf.File('france.osm.pbf') as osm:
        app = Application()
        app.parse(osm)

        with open('names.csv', 'w', encoding='UTF8', newline='') as f:
            writer = csv.writer(f)
            for k in sorted(app.names):
                l = [k]
                for i in app.names[k]:
                    l.append(i)
                writer.writerow(l)

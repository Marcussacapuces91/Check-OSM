import csv
import datetime
import logging
import re
import esy.osm.pbf
import requests
import json

from sympy import Point, Polygon, intersection


def _nwr(entry) -> str:
    return 'node' if type(entry) == esy.osm.pbf.file.Node else 'way' if type(
        entry) == esy.osm.pbf.file.Way else 'relation'

# @see https://josm.openstreetmap.de/wiki/Help/RemoteControlCommands

class Application:

    def __init__(self):
        self.names: dict
        self.errors: int

        logging.debug("Loading deprecated keys.")
        self._keys = list()
        with open('deprecated_keys.csv', newline='') as f:
            reader = csv.reader(f)
            next(reader)  # Saute la 1ère ligne
            for row in reader:
                self._keys.append(row[0])

        logging.debug("Loading deprecated tags.")
        self._tags = list()
        with open('deprecated_tags.csv', newline='') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                self._tags.append((row[0], row[1]))

        logging.debug("Loading exclusions.")
        with open('exclusions.csv', newline='') as f:
            reader = csv.reader(f)
            next(reader)  # Saute la 1ère ligne
            nodes = { int(row[0].split(' ')[1]) for row in reader if len(row[0].split(' ')) and row[0].split(' ')[0] == 'node' }

            f.seek(0)
            reader = csv.reader(f)
            next(reader)  # Saute la 1ère ligne
            ways = { int(row[0].split(' ')[1]) for row in reader if len(row[0].split(' ')) and row[0].split(' ')[0] == 'way' }

            f.seek(0)
            reader = csv.reader(f)
            next(reader)  # Saute la 1ère ligne
            relations = { int(row[0].split(' ')[1]) for row in reader if len(row[0].split(' ')) and row[0].split(' ')[0] == 'relation' }

        self._exclude = { 'node': nodes, 'way': ways, 'relation': relations }

    def add_names(self, entry):
        """Compte les libellés de 'name' dans une liste les regroupant tous."""
        n = entry.tags['name']
        try:
            self.names[n].add(f'{_nwr(entry)}/{entry.id}')
        except KeyError:
            self.names[n] = {f'{_nwr(entry)}/{entry.id}'}

    def name_egale_addr_housenumber(self, entry):
        """Recherche name = addr:housenumber"""
        try:
            if entry.tags['name'] == entry.tags['addr:housenumber']:
                if (type(entry) == esy.osm.pbf.file.Node and entry.id in ('121991199',)) or \
                   ('amenity' in entry.tags and entry.tags['amenity'] == 'restaurant'):
                    return  # Exceptions
                self.errors += 1
                logging.warning(
                    f"name = addr:housenumber ({entry.tags['name']})",
                    extra={'type': _nwr(entry), 'id': entry.id}
                )
                n = _nwr(entry) + str(entry.id)
                requests.get('http://localhost:8111/load_object', params={'objects': n})
        except KeyError:
            pass

    def name_egale_ref(self, entry):
        """Recherche name = addr:housenumber"""
        try:
            if entry.tags['name'] == entry.tags['ref']:
                self.errors += 1
                logging.warning(
                    f"name = ref ({entry.tags['name']})",
                    extra={'type': _nwr(entry), 'id': entry.id}
                )
                n = _nwr(entry) + str(entry.id)
                requests.get('http://localhost:8111/load_object', params={'objects': n})
        except KeyError:
            pass

    def name_commence_ou_termine_par_espace(self, entry):
        """name commence ou se termine par un espace"""
        if re.match(r'^\s', entry.tags['name']):
            self.errors += 1
            logging.error(
                f"'name' commence par un espace ({entry.tags['name']})",
                extra={'type': _nwr(entry), 'id': entry.id}
            )
        if re.match(r'\s$', entry.tags['name']):
            self.errors += 1
            logging.error(
                "'name' se termine par un espace ({entry.tags['name']})",
                extra={'type': _nwr(entry), 'id': entry.id}
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
            if re.match(r'^\d', entry.tags['name']):
                if \
                   re.match(f'^\d+ ({"|".join(mois)})', entry.tags['name']) or \
                   re.match(r'^(1er|1ère|\d+e|\d+è|\d+ème)\s', entry.tags['name']) or \
                   'amenity' in entry.tags or \
                   ('highway' in entry.tags and entry.tags['highway'] in ('bus_stop', )) or \
                   ('historic' in entry.tags and entry.tags['historic'] in ('memorial', )) or \
                   'office' in entry.tags or \
                   ('public_transport' in entry.tags and entry.tags['public_transport'] in ('stop_position', 'plateform')) or \
                   'razed:shop' in entry.tags or \
                   'shop' in entry.tags or \
                   ('tourism' in entry.tags and entry.tags['tourism'] in ('artwork', 'chalet', 'hotel')):
                    return # Exceptions à la règle
                self.errors += 1
                logging.warning(
                    f"'name' commence par un chiffre ({entry.tags['name']})",
                    extra={'type': _nwr(entry), 'id': entry.id}
                )
                n = _nwr(entry) + str(entry.id)
                requests.get('http://localhost:8111/load_object', params={'objects': n})


        except KeyError:
            pass

    def tag_deprecie(self, entry):
        """Tags (key/value) dépréciés"""
        for k in entry.tags:
            if (k, entry.tags[k]) in self._tags:
                self.errors += 1
                logging.info(
                    f"Tag \'{k}\'=\'{entry.tags[k]}\' déprécié ({entry.tags['name']})",
                    extra={'type': _nwr(entry), 'id': entry.id}
                )

    def key_deprecie(self, entry):
        """Key dépréciés"""
        for k in entry.tags:
            if k in self._keys:
                self.errors += 1
                logging.info(
                    f"Key \'{k}\' dépréciée ({entry.tags['name']})",
                    extra={'type': _nwr(entry), 'id': entry.id}
                )

    def check_name(self, entry):
        """Vérifie le contenu du champ name et sa validité"""
        highway_black_list = (
            r'^Chemin Ancien Chemin ',
            r'^Chemin Chemin ',
            r'^Chemin [Rr]ural (No|Numéro|n°|N°|№)',
            r'^Chemin Vicinal ',
            r'^Chemin d\'Exploitation ',
            r'Voie [Cc]ommunale (No|Numéro|n°|N°|№)',
            r'Voie Dite',
            f'Z\.? ?A\.?',
            f'Z\.? ?I\.?',
            r'^\w+ [A-Z]+\.',   # Abréviation
            r'^\w+ Georges Sand',
            r'^\w+ Pierre Ronsard',
            r'^\w+ Roger-Martin du Gard',   # sans tiret "Roger Martin du Gard"
            r'^\w+ Marroniers*',
            r'^\w+ D\'\w+',
            r'^\w+ De \w+',
            r'^\w+ Des \w+'
        )
        """Liste des noms de voies formellement erronées."""

        highway_type_valid_list = (
            'Allée', 'Autoroute', 'Avenue',
            'Basse Corniche', 'Belvédère', 'Boucle', 'Boulevard', 'Bretelle',
            'Carreau', 'Carrefour', 'Chasse', 'Chaussée', 'Chemin', '(Le|Nouveau|Ancien|Vieux) Chemin', 'Cité', 'Clos', 'Corniche', 'Cour', 'Cours', 'Côte', 'Contournement',
            'Descente', 'Déviation', 'Domaine',
            'Échangeur', 'Espace', 'Esplanade',
            'Faubourg',
            'Giratoire',
            'Hameau',
            'Impasse',
            'Jardins?',
            'Les Quatre Routes', 'Lotissement',
            'Mail', 'Montée',
            '(|Grande |Grand)Place', 'Parc', 'Parvis', 'Passage', 'Passerelle', 'Pénétrante', 'Périphérique', 'Pont', 'Port', 'Porte', 'Promenade',
            'Quai',
            'Résidence', 'Rocade', 'Rond-Point', '(|Grande |Vieille )Route', "(|Petite |Grand'|Grande )Rue",
            'Sente', 'Sentier', 'Square', 'Sortie',
            'Terrasse', 'Traverse', 'Tunnel',
            'Vallée', 'Viaduc', 'Villa', 'Voie',

# Alsace
            r'^[A-Z][a-z]* Pfad$',

            r'^[A-Z]\w*(gasse?| Weg|-Weg|weg| Pfad|pfad|strasse)$',
            r'^Alter [A-Z]\w*( Weg|weg| Pfad)$',
            r'^Einen [A-Z]\w*( Weg|weg| Pfad)$',
            r'^Grosser [A-Z]\w*( Weg|weg| Pfad)$',
            r'^Klein(er)? [A-Z]\w*( Weg|weg| Pfad)$',
            r'^Mittlerer [A-Z]\w*( Weg|weg| Pfad)$',
            r'^Oberer [A-Z]\w*( Weg|weg| Pfad)$',
            r'^Ober-[A-Z]\w*( Weg|weg| Pfad)$',
            r'^Unter[- ][A-Z]\w*( Weg|weg| Pfad)$',
            r'^Unterer [A-Z]\w*( Weg|weg| Pfad)$',
            r'^Vordere(r)? [A-Z]\w*( Weg|weg| Pfad)$',

            "L'Aquitaine", 'La Francilienne', 'L’Océane', "L'Européenne", 'La Comtoise', 'La Provençale',
            'La Languedocienne', 'La Méridienne', "L'Arverne", 'La Transeuropéenne', "L'Occitane", 'La Catalane',
        )
        """Liste des 1ers nom de voie usuels"""

        highway_value_list = (
            'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified', 'residential',
            'motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link',
            'living_street', 'pedestrian', 'track', 'bus_guideway', 'road', 'busway',
            # 'service'
        )
        """Types (tags) de voies auxquelles les tests de nommage s'appliquent."""

        try:
            if entry.tags['highway'] in highway_value_list:
                l = "|".join(highway_type_valid_list)
                if re.match(f'^({l})', entry.tags['name']):
                    for regle in highway_black_list:
                        if re.match(regle, entry.tags['name']):
                            self.errors += 1
                            logging.error(
                                f"Erreur/Typo sur nom de voie '{regle}' ({entry.tags['name']})",
                                extra={'type': _nwr(entry), 'id': entry.id}
                            )
                            n = _nwr(entry) + str(entry.id)
                            requests.get('http://localhost:8111/load_object', params={'objects': n})
                else:
                    self.errors += 1
                    logging.info(
                        f"Type de voie inconnue ({entry.tags['name']})",
                        extra={'type': _nwr(entry), 'id': entry.id}
                    )
                    n = _nwr(entry) + str(entry.id)
                    requests.get('http://localhost:8111/load_object', params={'objects': n})
        except KeyError:
            pass

    def parse_block(self, block_, nodes_: int, ways_: int, relations_: int) -> (int, int, int):
        for entry in block_:
            match type(entry):
                case esy.osm.pbf.file.Node:
                    if int(entry.id) in self._exclude['node']:
                        continue

                    nodes_ += 1
                    try:
                        self.add_names(entry)
                        self.check_name(entry)
                        #self.name_egale_addr_housenumber(entry)
                        #self.name_egale_ref(entry)
                        #self.name_commence_ou_termine_par_espace(entry)
                        #self.name_commence_par_un_chiffre(entry)
                    except KeyError:  # Pas de name
                        pass

                    # self.key_deprecie(entry)
                    # self.tag_deprecie(entry)

                case esy.osm.pbf.file.Way:
                    if int(entry.id) in self._exclude['way']:
                        continue

                    ways_ += 1
                    try:
                        self.add_names(entry)
                        self.check_name(entry)
                        #self.name_egale_addr_housenumber(entry)
                        #self.name_egale_ref(entry)
                        #self.name_commence_ou_termine_par_espace(entry)
                        #self.name_commence_par_un_chiffre(entry)
                    except KeyError:  # Pas de name
                        pass

                    # self.key_deprecie(entry)
                    # self.tag_deprecie(entry)

                case esy.osm.pbf.file.Relation:
                    if int(entry.id) in self._exclude['relation']:
                        continue

                    relations_ += 1
                    try:
                        self.add_names(entry)
                        self.check_name(entry)
                        #self.name_egale_ref(entry)
                        #self.name_commence_ou_termine_par_espace(entry)
                    except KeyError:  # Pas de name
                        pass

                    # self.key_deprecie(entry)
                    # self.tag_deprecie(entry)

        return nodes_, ways_, relations_

    def parse(self, file: esy.osm.pbf.File):
        logging.debug('Parsing fichier à vide.')
        blocks = list(file.blocks)
        size = len(blocks)
        nodes, ways, relations = 0, 0, 0
        self.errors = 0
        self.names = {}
        start = datetime.datetime.now()
        logging.debug('Parsing des blocs.')
        for i, block in enumerate(blocks):
            nodes, ways, relations = self.parse_block(block, nodes, ways, relations)
            now = datetime.datetime.now()
            end = start + (now - start) / ((i + 1) / size)
            print(f'{now.strftime("%H:%M:%S")} ({(i + 1) / size:3.2%}) -> {end.strftime("%H:%M")} :',
                  f'Names : {len(self.names)}, Errors : {self.errors}',
                  f'- Nodes : {nodes:,} - Ways : {ways:,} - Rels : {relations:,}')
        logging.debug('Parsing terminé.')


if __name__ == '__main__':
    FORMAT = '%(asctime)s [%(lineno)5d] %(levelname)8s - %(funcName)s - %(message)s ' \
             'https://www.openstreetmap.org/%(type)s/%(id)s'
#    logging.basicConfig(filename='openstreetmap.log', filemode='w', encoding='utf-8', level=logging.DEBUG,
#                        format=FORMAT)
    logging.basicConfig(encoding='utf-8', level=logging.DEBUG+1)

    app = Application()

    with esy.osm.pbf.File('alsace.osm.pbf') as osm:
        app.parse(osm)

    with open('names.csv', 'w', encoding='UTF8', newline='') as f:
        writer = csv.writer(f)
        for k in sorted(app.names):
            l = [k]
            for i in app.names[k]:
                l.append(i)
            writer.writerow(l)

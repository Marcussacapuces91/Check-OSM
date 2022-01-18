import csv
import datetime
import logging
import re
import esy.osm.pbf
import requests
# import json

# from sympy import Point, Polygon, intersection


def _nwr(entry) -> str:
    return 'node' if type(entry) == esy.osm.pbf.file.Node else 'way' if type(
        entry) == esy.osm.pbf.file.Way else 'relation'

# @see https://josm.openstreetmap.de/wiki/Help/RemoteControlCommands


class Application:

    def __init__(self):
        self.errors: int = 0
        self.names: dict = {}

        logging.debug("Loading deprecated keys.")
        self._keys = list()
        with open('deprecated_keys.csv', newline='') as f_deprec:
            reader = csv.reader(f_deprec)
            next(reader)  # Saute la 1ère ligne
            for row in reader:
                self._keys.append(row[0])

        logging.debug("Loading deprecated tags.")
        self._tags = list()
        with open('deprecated_tags.csv', newline='') as f_deprec:
            reader = csv.reader(f_deprec)
            next(reader)
            for row in reader:
                self._tags.append((row[0], row[1]))

        logging.debug("Loading exclusions.")
        with open('exclusions.csv', newline='') as f:
            reader = csv.reader(f)
            next(reader)  # Saute la 1ère ligne
            nodes = {
                int(row[0].split(' ')[1])
                for row in reader
                if len(row[0].split(' ')) and row[0].split(' ')[0] == 'node'
            }

            f.seek(0)
            reader = csv.reader(f)
            next(reader)  # Saute la 1ère ligne
            ways = {
                int(row[0].split(' ')[1])
                for row in reader
                if len(row[0].split(' ')) and row[0].split(' ')[0] == 'way'
            }

            f.seek(0)
            reader = csv.reader(f)
            next(reader)  # Saute la 1ère ligne
            relations = {
                int(row[0].split(' ')[1])
                for row in reader
                if len(row[0].split(' ')) and row[0].split(' ')[0] == 'relation'
            }

        self._exclude = {'node': nodes, 'way': ways, 'relation': relations}

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
                if (
                   re.match(f'^\\d+ ({"|".join(mois)})', entry.tags['name']) or
                   re.match(r'^(1er|1ère|\d+e|\d+è|\d+ème)\s', entry.tags['name']) or
                   'amenity' in entry.tags or
                   ('highway' in entry.tags and entry.tags['highway'] in ('bus_stop', )) or
                   ('historic' in entry.tags and entry.tags['historic'] in ('memorial', )) or
                   'office' in entry.tags or
                   ('public_transport' in entry.tags and
                        entry.tags['public_transport'] in ('stop_position', 'plateform')) or
                   'razed:shop' in entry.tags or
                   'shop' in entry.tags or
                   ('tourism' in entry.tags and entry.tags['tourism'] in ('artwork', 'chalet', 'hotel'))
                   ):
                    return  # Exceptions à la règle
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
        for tag in entry.tags:
            if (tag, entry.tags[tag]) in self._tags:
                self.errors += 1
                logging.info(
                    f"Tag \'{tag}\'=\'{entry.tags[tag]}\' déprécié ({entry.tags['name']})",
                    extra={'type': _nwr(entry), 'id': entry.id}
                )

    def key_deprecie(self, entry):
        """Key dépréciés"""
        for tag in entry.tags:
            if tag in self._keys:
                self.errors += 1
                logging.info(
                    f"Key \'{tag}\' dépréciée ({entry.tags['name']})",
                    extra={'type': _nwr(entry), 'id': entry.id}
                )

    def check_name(self, entry):
        """Vérifie le contenu du champ name et sa validité"""
        highway_black_list = {
            r'^\d+',
            r'^\w+\.',
            r'^all([eé]e|eé)',
            r'^avenue',
            r'^[Cc]h\.?\s',
            r'^[Cc]hemin [Aa]ncien [Cc]hemin',
            r'^[Cc]hemin [Cc]hemin',
            r'^[Cc]hemin [Rr]ural (No|Numéro|n°|N°|№)',
            r'^[Cc]hemin [Vv]icinal',
            r'^[Cc]hemin d\'[Ee]xploitation',
            r'^chemin',
            r'^(C|CE|CR|D|G[Rr]|N) ?\d+',
            r"l'[Ee]rable",
            r'^Lotossement', r'^Lotiseement',
            r'maître \w+',
            r'passage',
            r'^Qrt',
            r'Résdence',
            r'^RUE', r'^rue',
            r'^ROUTE', r'^route',
            r'^[Rr]oute [Dd]épartementale (No|Numéro|n°|N°|№)',
            r'[Ss]t[e] Anne',
            r'^[Vv]oie [Cc]ommunale (No|Numéro|n°|N°|№)',
            r'^VC',
            r'^[Vv]oie [Dd]ite',
            r'^voie',
            r'^[Zz]\.? ?[Aa][CcEe]?.?\s',
            r'^[Zz]\.? ?[Cc].?\s',
            r'^[Zz]\.? ?[Ii].?\s',
            r'^\w+ [A-Z]+\.',   # Abréviation
            r'^\w+ Georges Sand',
            r'^\w+ Pierre Ronsard',
            r'^\w+ Roger-Martin du Gard',   # sans tiret "Roger Martin du Gard"
            r'^\w+ Marroniers*',
            r'^\w+ D\'\w+',
            r'^\w+ De \w+',
            r'^\w+ Des \w+',
        }
        """Set des noms de voies formellement erronées."""

        highway_type_valid_list = {
            '^(Grande )?Allée', '^Autoroute', r'^Avenue\s',
            '^Belvédère', '^Boucle', r'^Boulevard\s', '^Bretelle',
            '^Carreau', '^Carrefour', '^Chasse', '^Chaussée', '^(Ancien |Grand |Le |Nouveau |Petit |Vieux )?Chemin',
            '^Cité', '^Circuit', '^Clos', '^(Basse )?Corniche', '^Cour', '^Cours', '^(Vieille )?Côte', '^Contournement',
            '^Descente', '^Déviation', '^Diffuseur', '^Domaine',
            '^Échangeur', '^Espace', '^Esplanade', '^Eurovélo',
            r'^Faubourg\s', '^Fossé',
            '^Giratoire', '^Gué',
            '^Hameau',
            '^Impasse', '^Itinéraire',
            '^Jardins?',
            '^Les Quatre Routes', '^Lieu-dit', '^Lotissement',
            '^Mail', '^Montée',
            '^Parc', '^Parvis', '^Passage', '^Passe', '^Passerelle', "^(Ancienne |Grande |Grand'?|Petite )?Place",
            '^Pénétrante', '^Périphérique', '^Pont', '^Port', '^Porte', '^Promenade',
            '^Quartier', '^Quai',
            '^Résidence', '^Rocade', '^Rond-Point', '^(Ancienne |Grande |Petite |Vieille )?Route',
            "^(Basse |Grand[' ]|Grande |Haute |Petite |Vieille )?Rue",
            '^Sente', '^Sentier', '^Square', '^Sortie',
            '^Terrasse', '^Traverse', '^Tranchée', '^Tunnel',
            '^Vallée', '^Venelle', '^Véloroute', '^Viaduc', '^Villa', '^(Ancienne )?Voie',
            '^Zone Artisanale', "^Zone d'Activité", '^Zone Industrielle',

            # Nord
            '^Ratzengaesschen', '.* Straete$', '.*stra[ae]t$', '.*dreve$',

            # Alsace
            r'^(|Alter? |Einen |Grosser |Klein(er)? |Le |Mittel |Mittlerer |Oberer |Ober[- ]|Unter[- ]|Unterer ' + \
            r'|Vorderer?)[A-Z].*( Gasse|gasse?| Pfad|pfad|strasse| Weg|-Weg|weg)$',
            '^Engpfaede$',

            # Autoroutes nationales
            "^L'Aquitaine$", '^La Francilienne$', '^L’Océane$', "^L'Européenne$", '^La Comtoise$', '^La Provençale$',
            '^La Languedocienne$', '^La Méridienne$', "^L'Arverne$", '^La Transeuropéenne$', "^L'Occitane$",
            '^La Catalane$', "^L'Autoroute de l'Arbre$", '^La Pyrénéenne$', "^L'Armoricaine$", "^L'Ariégeoise$",
        }
        """Set des noms de voies acceptés"""

        highway_value_list = (
            'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified', 'residential',
            'motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link',
            'living_street', 'pedestrian', 'bus_guideway', 'road', 'busway',
            # 'service', 'track'
        )
        """Types (tags) de voies auxquelles les tests de nommage s'appliquent."""

        try:
            if entry.tags['highway'] in highway_value_list:
                # Test black-list
                for black in highway_black_list:
                    # print(black)
                    if re.match(black, entry.tags['name']):
                        self.errors += 1
                        logging.error(
                            f"Erreur/Typo sur nom de voie '{black}' ({entry.tags['name']})",
                            extra={'type': _nwr(entry), 'id': entry.id}
                        )
                        n = _nwr(entry) + str(entry.id)
                        requests.get('http://localhost:8111/load_object', params={'objects': n})
                        return
                if True:    # Utilisation de la white-list ?
                    # Pas de black -> test white-list
                    for valid in highway_type_valid_list:
                        if re.match(valid, entry.tags['name']): # OK
                            return
                    # Pas trouvé en white-list -> erreur
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
                        # self.name_egale_addr_housenumber(entry)
                        # self.name_egale_ref(entry)
                        # self.name_commence_ou_termine_par_espace(entry)
                        # self.name_commence_par_un_chiffre(entry)
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
                        # self.name_egale_addr_housenumber(entry)
                        # self.name_egale_ref(entry)
                        # self.name_commence_ou_termine_par_espace(entry)
                        # self.name_commence_par_un_chiffre(entry)
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
                        # self.name_egale_ref(entry)
                        # self.name_commence_ou_termine_par_espace(entry)
                    except KeyError:  # Pas de name
                        pass

                    # self.key_deprecie(entry)
                    # self.tag_deprecie(entry)

        return nodes_, ways_, relations_

    def parse(self, file: esy.osm.pbf.File) -> None:
        """Analyse tout le fichier transmis en 2 passes (1 Collecte des blocs (et taille), 2 analyse des blocs"""
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

    def save_names(self, filename: str):
        """Sauvegarde la liste de tous les noms (tag name) collectés"""
        with open(filename, 'w', encoding='UTF8', newline='') as f:
            writer = csv.writer(f)
            for k in sorted(self.names):
                ligne = [k]
                for i in self.names[k]:
                    ligne.append(i)
                writer.writerow(ligne)


if __name__ == '__main__':
    FORMAT = '%(asctime)s [%(lineno)5d] %(levelname)8s - %(funcName)s - %(message)s ' \
             'https://www.openstreetmap.org/%(type)s/%(id)s'
#    logging.basicConfig(filename='openstreetmap.log', filemode='w', encoding='utf-8', level=logging.DEBUG,
#                        format=FORMAT)
    logging.basicConfig(encoding='utf-8', level=logging.DEBUG+1)

    app = Application()

    liste = {
        'nord', 'ardennes', 'meuse', 'meurthe_et_moselle', 'moselle', 'bas_rhin', 'haut_rhin', 'doubs', 'jura',
        'ain', 'haute_savoie', 'savoie', 'hautes_alpes', 'alpes_de_haute_provence', 'alpes_maritimes', 'var',
        'pyrenees_orientales', 'ariege', 'haute_garonne', 'hautes_pyrenees', 'pyrenees_atlantiques'
    }
    liste = { 'essonne' }
    for n in liste:
        with esy.osm.pbf.File(f'{n}.osm.pbf') as osm_pbf:
            app.names = {}
            app.parse(osm_pbf)
            app.save_names(f'names_{n}.csv')

import csv
import datetime
import logging
import re
import xml.etree.ElementTree

import esy.osm.pbf
import requests


def _nwr(entry) -> str:
    return 'node' if type(entry) == esy.osm.pbf.file.Node else 'way' if type(
        entry) == esy.osm.pbf.file.Way else 'relation'

# @see https://josm.openstreetmap.de/wiki/Help/RemoteControlCommands


class Application:

    def __init__(self):
        self.errors: int = 0
        self.names: dict = {}

        logging.debug("Loading deprecated keys.")
        self._deprecated_keys = list()
        with open('deprecated_keys.csv', newline='', encoding="utf8") as f_deprec:
            reader = csv.reader(f_deprec)
            next(reader)  # Saute la 1ère ligne
            self._deprecated_keys = (row[0] for row in reader)

        logging.debug("Loading deprecated tags.")
        self._deprecated_tags = list()
        with open('deprecated_tags.csv', newline='', encoding="utf8") as f_deprec:
            reader = csv.reader(f_deprec)
            next(reader)
            self._deprecated = (
                (row[0], row[1]) for row in reader
            )

        logging.debug("Loading exclusions.")
        with open('exclusions.csv', newline='', encoding="utf8") as f:
            reader = csv.reader(f)
            next(reader)  # Saute la 1ère ligne
            nodes = frozenset(
                int(row[0].split(' ')[1])
                for row in reader
                if len(row) and len(row[0].split(' ')) and row[0].split(' ')[0] == 'node'
            )

            f.seek(0)
            reader = csv.reader(f)
            next(reader)  # Saute la 1ère ligne
            ways = frozenset(
                int(row[0].split(' ')[1])
                for row in reader
                if len(row) and len(row[0].split(' ')) and row[0].split(' ')[0] == 'way'
            )

            f.seek(0)
            reader = csv.reader(f)
            next(reader)  # Saute la 1ère ligne
            relations = frozenset(
                int(row[0].split(' ')[1])
                for row in reader
                if len(row) and len(row[0].split(' ')) and row[0].split(' ')[0] == 'relation'
            )

        self._exclude = {'node': nodes, 'way': ways, 'relation': relations}

        logging.debug("Loading invalid ways name.")
        with open('invalid_ways_name.csv', newline='', encoding="utf8") as f:
            reader = csv.reader(f)
            next(reader)  # Saute la 1ère ligne

            l_: list = []
            for row in reader:
                if len(row) and row[0][0] != '#':
                    try:
                        r0 = re.compile(row[0])
                    except re.error as e:
                        raise(Exception(f'{e} : "{row[0]}"'))
                    if len(row) == 1:
                        l_.append((r0,))
                    else:
                        l_.append((r0, row[1]))
            self._invalid_ways_name = frozenset(l_)
#            for r in self._invalid_ways_name:
#                print(r)
#            exit(0)

    def add_names(self, entry):
        """Compte les libellés de 'name' dans une liste les regroupant tous."""
        name = entry.tags['name']
        try:
            self.names[name].add(f'{_nwr(entry)}/{entry.id}')
        except KeyError:
            self.names[name] = {f'{_nwr(entry)}/{entry.id}'}

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
                requests.get(
                    'http://localhost:8111/load_object',
                    params={'objects': _nwr(entry) + str(entry.id)}
                )
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
                requests.get(
                    'http://localhost:8111/load_object',
                    params={'objects': _nwr(entry) + str(entry.id)}
                )
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
                   ('tourism' in entry.tags and
                        entry.tags['tourism'] in ('artwork', 'chalet', 'hotel'))
                   ):
                    return  # Exceptions à la règle
                self.errors += 1
                logging.warning(
                    f"'name' commence par un chiffre ({entry.tags['name']})",
                    extra={'type': _nwr(entry), 'id': entry.id}
                )
                requests.get(
                    'http://localhost:8111/load_object',
                    params={'objects': _nwr(entry) + str(entry.id)}
                )

        except KeyError:
            pass

    def tag_deprecie(self, entry):
        """Tags (key/value) dépréciés"""
        for tag in entry.tags:
            if (tag, entry.tags[tag]) in self._deprecated_tags:
                self.errors += 1
                logging.info(
                    f"Tag \'{tag}\'=\'{entry.tags[tag]}\' déprécié ({entry.tags['name']})",
                    extra={'type': _nwr(entry), 'id': entry.id}
                )

    def key_deprecie(self, entry):
        """Key dépréciés"""
        for tag in entry.tags:
            if tag in self._deprecated_keys:
                self.errors += 1
                logging.info(
                    f"Key \'{tag}\' dépréciée ({entry.tags['name']})",
                    extra={'type': _nwr(entry), 'id': entry.id}
                )

    def check_highway_name(self, entry):
        """Pour un sous-ensemble des highway, vérifie le contenu du champ name et sa validité"""

        # highway_type_valid_list = {
        #     '^Abbaye', '^(Grande )?Allée', '^Autoroute', r'^(Petite )?Avenue\s',
        #     '^Belvédère', '^Boucle', r'^Boulevard\s', '^(Le )?Bois', '^Bretelle',
        #     '^Carreau', '^Carrefour', '^Chasse', '^Chaussée', '^Château',
        #     '^(Ancien |Grand |Ancien Grand |Le |Nouveau |Petit |Vieux )?Chemin',
        #     '^Cité', '^Circuit', '^Cloître', '^Clos', '^Col', '^(Basse )?Corniche', '^(Grande )?Cour', '^Cours',
        #     '^(Vieille )?Côte', '^Contournement', '^Coulée', '^Croisement',
        #     '^(Ancienne )?Départementale', '^Descente', '^Desserte', '^Déviation', '^Diffuseur', '^Domaine',
        #     '^Duplex',
        #     '^Échangeur', '^Escalier', '^Espace', '^Esplanade', '^Eurovélo',
        #     r'^Faubourg\s', '^Fossé',
        #     '^(Grand )?Giratoire', '^Gué',
        #     '^Hameau',
        #     '^(Petite )?Impass?e', '^Itinéraire',
        #     '^Jardins?',
        #     '^Levée', '^Les Quatre Routes', '^Lieu-dit', '^Lotissement',
        #     '^Mail', '^Montée', '^Montoir',
        #     '^Parc', '^Parking', '^Parvis', '^Passage', '^Passe', '^Passerelle',
        #     "^(Ancienne |Grande |Grand'?|Petite )?Place", '^Placette',
        #     '^Patio', '^Pénétrante', '^Périphérique', '^Piste', '^(Grand )?Pont', '^Port', '^Porte', '^Promenade',
        #     '^Quartier', '^Quai',
        #     '^Rampe', '^Résidence', '^Ring', '^Rocade', '^Rond-Point', '^(Ancienne |Grande |Petite |Vieille )?Route',
        #     "^(Basse |Grand( |'|' )|Grande |Haute |Petite |Nouvelle |Vieille )?Rue",
        #     '^(Grande )?Sente', '^Sentier', '^Square', '^Sortie',
        #     '^Terrasse', '^Traverse', '^Tranchée', '^Traverse', '^Tube', '^Tunnel',
        #     '^Vallée', '^Vallon', '^Venelle', '^Véloroute', '^Viaduc', '^Villa',
        #     '^(Ancienne |Petite |Nouvelle )?Voie',
        #     '^Voirie',
        #     '^Zone Artisanale', "^Zone d'Activité", '^Zone Industrielle',
        #
        #     # Nord
        #     '^Ratzengaesschen', '.* Straete$', '.*stra[ae]t$', '.*dreve$',
        #
        #     # Alsace
        #     r'^(|Alter? |Einen |Grosser |Klein(er)? |Le |Mittel |Mittlerer |Oberer |Ober[- ]|Unter[- ]|Unterer ' + \
        #     r'|Vorderer?)[A-Z].*( Gasse|gasse?| Pfad|pfad|strasse| Weg|-Weg|weg)$',
        #     '^Engpfaede$',
        #
        #     # Autoroutes nationales
        #     "^L'Aquitaine$", '^La Francilienne$', '^L’Océane$', "^L'Européenne$", '^La Comtoise$', '^La Provençale$',
        #     '^La Languedocienne$', '^La Méridienne$', "^L'Arverne$", '^La Transeuropéenne$', "^L'Occitane$",
        #     '^La Catalane$', "^L'Autoroute de l'Arbre$", '^La Pyrénéenne$', "^L'Armoricaine$", "^L'Ariégeoise$",
        # }
        # """Set des noms de voies acceptés"""

        highway_value_list = (
            'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified', 'residential',
            'motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link',
            'living_street', 'pedestrian', 'bus_guideway', 'road', 'busway',
            'path',
            # 'service', 'track'
        )
        """Types (tags) de voies auxquelles les tests de nommage s'appliquent."""

        def check_name(key: str, value: str, entry_) -> str:
            # 1er tour pour chercher 1 match
            change = False
            for row in self._invalid_ways_name:
                if len(row) == 2:
                    match = row[0].search(value)
                    if match:
                        replace = match.expand(row[1])
                        if replace != value:
                            change = True
                            root = xml.etree.ElementTree.fromstring(
                                requests.get(
                                    f'https://api.openstreetmap.org/api/0.6/{_nwr(entry_)}/{entry_.id}'
                                ).content
                            )
                            match root[0].tag:
                                case 'node':
                                    entry_ = esy.osm.pbf.Node(
                                        id=root[0].attrib['id'],
                                        tags={i.attrib['k']: i.attrib['v'] for i in root[0].iter('tag')},
                                        lonlat=(float(root[0].attrib['lon']), float(root[0].attrib['lat']))
                                    )
                                case 'way':
                                    entry_ = esy.osm.pbf.Way(
                                        id=root[0].attrib['id'],
                                        tags={i.attrib['k']: i.attrib['v'] for i in root[0].iter('tag')},
                                        refs=None
                                    )
                                case 'relation':
                                    entry_ = esy.osm.pbf.Relation(
                                        id=root[0].attrib['id'],
                                        tags={i.attrib['k']: i.attrib['v'] for i in root[0].iter('tag')},
                                        members=None
                                    )
                            break
            if not change:
                return value

            while True:  # Repeat search until no more
                start = value
                for row in self._invalid_ways_name:
                    match = row[0].search(value)
                    if match:
                        if len(row) == 1:     # search
                            self.errors += 1
                            logging.warning(f'Erreur/Typo "{row[0].pattern}" sur "{key}"="{value}"')
                            requests.get(
                                'http://localhost:8111/load_object',
                                params={'objects': _nwr(entry_) + str(entry_.id)}
                            )
                            return value
                        elif len(row) == 2:   # search & replace
                            try:
                                replace = match.expand(row[1])
                            except re.error as e:
                                print(f'{e} : {row[1]}')
                                raise e
                            if replace != value:
                                self.errors += 1
                                logging.error(
                                    f'Correction/Typo "{row[0].pattern}" sur "{key}"="{value}" -> "{replace}"'
                                )
                                requests.get(
                                    'http://localhost:8111/load_object',
                                    params={
                                        'objects': _nwr(entry_) + str(entry_.id),
                                        'addtags': f'{key}={replace}'
                                    }
                                )
                                value = replace
                                #break
                if start == value:
                    return value

        try:
            match entry:
                case esy.osm.pbf.file.Node():
                    check_name('addr:street', entry.tags['addr:street'], entry)

                case esy.osm.pbf.file.Way() if entry.tags['highway'] in highway_value_list:
                    check_name('name', entry.tags['name'], entry)

                case esy.osm.pbf.file.Relation() if entry.tags['type'] == 'associatedStreet':
                    check_name('name', entry.tags['name'], entry)
        except KeyError:
            pass

        # if False:    # Utilisation de la white-list ?
        #     try:
        #         # Pas de black -> test white-list
        #         for valid in highway_type_valid_list:
        #             if re.match(valid, entry.tags['name']):     # OK
        #                 return
        #         # Pas trouvé en white-list -> erreur
        #         self.errors += 1
        #         logging.info(
        #             f"Type de voie inconnue ({entry.tags['name']})",
        #             extra={'type': _nwr(entry), 'id': entry.id}
        #         )
        #         # n = _nwr(entry) + str(entry.id)
        #         # requests.get('http://localhost:8111/load_object', params={'objects': n})
        #     except KeyError:
        #         pass

    def parse_block(self, block_, nodes_: int, ways_: int, relations_: int) -> (int, int, int):
        for entry in block_:
            match type(entry):
                case esy.osm.pbf.file.Node:
                    if int(entry.id) in self._exclude['node']:
                        continue

                    nodes_ += 1
                    try:
                        self.add_names(entry)
                        # self.name_egale_addr_housenumber(entry)
                        # self.name_egale_ref(entry)
                        # self.name_commence_ou_termine_par_espace(entry)
                        # self.name_commence_par_un_chiffre(entry)
                    except KeyError:  # Pas de name
                        pass

                    self.check_highway_name(entry)
                    # self.key_deprecie(entry)
                    # self.tag_deprecie(entry)

                case esy.osm.pbf.file.Way:
                    if int(entry.id) in self._exclude['way']:
                        continue

                    ways_ += 1
                    try:
                        self.add_names(entry)
                        # self.name_egale_addr_housenumber(entry)
                        # self.name_egale_ref(entry)
                        # self.name_commence_ou_termine_par_espace(entry)
                        # self.name_commence_par_un_chiffre(entry)
                    except KeyError:  # Pas de name
                        pass

                    self.check_highway_name(entry)
                    # self.key_deprecie(entry)
                    # self.tag_deprecie(entry)

                case esy.osm.pbf.file.Relation:
                    if int(entry.id) in self._exclude['relation']:
                        continue

                    relations_ += 1
                    try:
                        self.add_names(entry)
                        # self.name_egale_ref(entry)
                        # self.name_commence_ou_termine_par_espace(entry)
                    except KeyError:  # Pas de name
                        pass

                    self.check_highway_name(entry)
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
        # for i, block in enumerate(blocks[56600:]):
        for i, block in enumerate(blocks):
            nodes, ways, relations = self.parse_block(block, nodes, ways, relations)
            now = datetime.datetime.now()
            end = start + (now - start) / ((i + 1) / size)
            print(i, f'{now.strftime("%H:%M:%S")} ({(i + 1) / size:3.2%}) -> {end.strftime("%H:%M")} :',
                  f'Names : {len(self.names)}, Errors : {self.errors}',
                  f'- Nodes : {nodes:,} - Ways : {ways:,} - Rels : {relations:,}')
        logging.debug('Parsing terminé.')

    def save_names(self, filename_: str):
        """Sauvegarde la liste de tous les noms (tag name) collectés"""
        with open(filename_, 'w', encoding='UTF8', newline='') as f:
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
    logging.basicConfig(
        filename='openstreetmap.log', filemode='w', encoding='utf-8',
        level=logging.DEBUG+1,
        format=r'%(asctime)s [%(lineno)5d] %(levelname)8s - %(funcName)s - %(message)s'
    )

    app = Application()
    requests.get(
        'http://localhost:8111/load_object',
        params={
            'objects': {'r/1403916'},
            'addtags': {'name': 'France métropolitaine'}
        }
    )
    # liste = {
    #     'nord', 'ardennes', 'meuse', 'meurthe_et_moselle', 'moselle', 'bas_rhin', 'haut_rhin', 'doubs', 'jura',
    #     'ain', 'haute_savoie', 'savoie', 'hautes_alpes', 'alpes_de_haute_provence', 'alpes_maritimes', 'var',
    #     'pyrenees_orientales', 'ariege', 'haute_garonne', 'hautes_pyrenees', 'pyrenees_atlantiques'
    # }
    # liste = {'essonne', 'ile_de_france'}
    liste = {'france'}
    for filename in liste:
        with esy.osm.pbf.File(f'{filename}.osm.pbf') as osm_pbf:
            app.names = {}
            app.parse(osm_pbf)
            app.save_names(f'names_{filename}.csv')

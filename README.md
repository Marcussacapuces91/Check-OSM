# Check OSM
 
Un bot (robot) qui vérifie, voir corrige certains éléments détectés dans OSM.
1. Analyse les libellés des éléments de type highway (node & addr:street ou way & name ou encore relation & name).
  L'accent est mis sur les typos et les erreurs de casse, incluant les accentués.
  Le fichier https://github.com/Marcussacapuces91/Check-OSM/raw/main/invalid_ways_name.csv paramètre ces détections (une seule colonne) ou corrections (deux colonnes).

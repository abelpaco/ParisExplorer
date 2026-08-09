# Format d'un sujet BD (Shorts « ligne claire »)

Un sujet BD = un fichier YAML dans `content/bd/`. Il devient un Short vertical
de 45 a 90 secondes : une carte de couverture, une carte par scene, une carte
finale — chaque carte affichee le temps exact de sa phrase dite par la voix
off. Les PNG des cartes alimentent aussi les posts Communaute.

Production : `python bd_cards.py <id> --lang fr` puis `--lang en`.
Le Short entre ensuite dans le calendrier normal (`plan_week.py`) sous la cle
de registre `<id>:<langue>:short-1`.

## Pourquoi un schema a part

Un sujet video decrit une narration de 350 mots et des requetes d'images
Wikimedia. Un sujet BD decrit un PORTRAIT et des SCENES : rien a voir. Tout
est dessine par le pipeline — **aucune image externe, aucun credit, aucune
licence a verifier**. C'est le format le plus sur juridiquement de toute la
chaine.

## Regles

- **`id`** : kebab-case, stable, JAMAIS renomme apres publication (meme regle
  que les sujets video — c'est la cle du registre anti-republication).
  L'identifiant porte l'angle : `moliere-naissance`, pas `moliere`.
- **`kind`** : `naissance` (une personne, avec `portrait` obligatoire) ou
  `anniversaire` (un evenement, avec `icon`).
- **`genre`** : `m` ou `f` — n'accorde QUE le bandeau (« d'un Parisien /
  d'une Parisienne »).
- **`anchor_date`** : MM-JJ. Le planificateur ne place le sujet QUE ce
  jour-la, en tete des creneaux. Produire AVANT la date, sinon c'est pour
  l'annee suivante.
- **`status`** : `draft` tant que les textes ne sont pas relus.
- **Bilingue** : bloc `fr` obligatoire, `en` fortement recommande.

## Le style : « ligne claire », jamais « style Herge »

Le trait est celui de l'ecole franco-belge : c'est un STYLE, il est libre.
Dans les titres, descriptions et posts, ecrire « ligne claire » ou « BD
franco-belge ». Ne JAMAIS ecrire « Herge » ou « Tintin » : l'ayant droit
(Tintinimaginatio) est notoirement procedurier, et le nom n'apporte rien que
le dessin ne montre deja.

## Le portrait evoque, il ne photographie pas

Le portrait se compose par attributs — c'est ce qui le rend fabricable en une
commande, et c'est assume : on reconnait Moliere a sa perruque et a sa mouche,
pas a la forme exacte de son nez. Choisir les DEUX ou TROIS attributs
signature de la personne et s'y tenir.

Vocabulaire (defini dans `bd_style.py`, valide au chargement) :

| Champ | Valeurs |
|---|---|
| `cheveux` | `perruque`, `mi-longs`, `courts`, `chignon`, `chauve` |
| `pilosite` | `moustache-fine`, `moustache-epaisse`, `barbe`, `bouc`, `mouche`, `favoris` |
| `costume` | `habit-ancien`, `redingote`, `robe`, `moderne`, `uniforme` |
| `accessoires` | `lunettes`, `beret`, `noeud`, `boucles-oreilles` |

Pictogrammes de scene : `plume`, `masque`, `couronne`, `livre`, `etoile`,
`tour-eiffel`, `notre-dame`, `coeur`, `eclair`, `musique`, `horloge`.

## Les scenes font la duree

3 a 8 scenes. Chaque scene = une phrase de 12 a 25 mots, ECRITE POUR ETRE
DITE : c'est la voix off qui la lit, et la carte reste affichee exactement ce
temps-la. Compter grossierement 6 a 9 secondes par carte : 5 scenes + la
couverture + la finale font 50 a 65 secondes. Le pipeline previent si le
total sort de la fenetre 45-90 s.

`hook` (couverture) pose la scene en une ou deux phrases ; `fact` (finale)
est LE fait qu'on retient. Ne pas repeter l'un dans l'autre.

## Exemple complet

Voir `moliere-naissance.yaml` dans ce dossier — c'est le sujet de reference,
produit et valide.

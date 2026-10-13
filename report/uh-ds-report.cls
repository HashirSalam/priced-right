\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{uh-ds-report}[2026/09/01 DS reports]

\newif\if@finnish%
\newif\if@swedish%
\newif\if@english%
\@finnishfalse\@swedishfalse\@englishfalse%

% Data science specific content starts
\newif\if@dsm\@dsmfalse
\newif\if@manual\@manualfalse
\newif\if@censored\@censoredfalse

\DeclareOption{finnish}{\@finnishtrue}
\DeclareOption{swedish}{\@swedishtrue}
\DeclareOption{english}{\@englishtrue}

\DeclareOption{dsm}{\@dsmtrue}
\DeclareOption{manual}{\@manualtrue}
\DeclareOption{censored}{\@censoredtrue}

% Data science specific content ends

\newif\if@oneside
\newif\if@twoside
\@onesidefalse
\@twosidetrue
\newif\if@defaulttypesize
\@defaulttypesizetrue

\DeclareOption{oneside}{\@onesidetrue\@twosidefalse}
\DeclareOption{twoside}{\@twosidetrue\@onesidefalse}

\DeclareOption{10pt}{
  \@defaulttypesizefalse
  \PassOptionsToClass{10pt}{report}}
\DeclareOption{11pt}{
  \@defaulttypesizefalse
  \PassOptionsToClass{11pt}{report}}
\DeclareOption{12pt}{
  \@defaulttypesizefalse
  \PassOptionsToClass{12pt}{report}}
\DeclareOption{a4paper}{
  \PassOptionsToClass{a4paper}{report}}
\if@defaulttypesize
  \PassOptionsToClass{12pt}{report}
\fi

\DeclareOption*{\PassOptionsToClass{\CurrentOption}{report}}

\ProcessOptions\relax

%% Programme specific options

\if@dsm
    \newcommand{\level}{\translate{dsm-level}}
    \newcommand{\programme}{\translate{dsm-programme}}
\fi
\if@manual
    \newcommand{\level}{\translate{instructions}}
    \newcommand{\programme}{\translate{dsm-programme}}
\fi
\newcommand{\oppiaine}{{Koulutusohjelma --- Utbildningsprogram  --- Study programme}}
\newcommand{\getSubject}{\programme}

\LoadClass{report}

\RequirePackage{refcount}

%%%% Trilanguage handling

\RequirePackage{translator}  % see the 3 files of translator-UHCSthesis
\usedictionary{template/translator-UHDSreport-coverpage-dictionary}

%% Tagging status language dependant, Finnish/Swedish/English should be ok
\if@finnish
  \RequirePackage[english,swedish,main=finnish]{babel}
  \selectlanguage{finnish}
\else
  \if@english
    \RequirePackage[swedish,finnish,main=english]{babel}
    \selectlanguage{english}
   \else
    \if@swedish
      \RequirePackage[finnish,english,main=swedish]{babel}
      \selectlanguage{swedish}
    \fi
  \fi
\fi

%% Page geometry
\RequirePackage{geometry}
\newcommand{\defaultsettings}{%
  \if@twoside
    \geometry{bindingoffset=0.5cm, top=2.5cm, left=2.5cm, right=2.5cm,
              textheight=23cm,
              headheight=0.5cm, headsep=0.5cm}%
  \else
    \geometry{top=2.5cm, left=2.5cm, right=2.5cm,
              textheight=23cm,
              headheight=0.5cm, headsep=0.5cm}%
  \fi
}
\defaultsettings

\setlength{\parindent}{0pt}
\setlength{\parskip}{1ex}

\RequirePackage{setspace}
%
% Theoretically broken with tagging if using fillable forms;
% Should otherwise be ok: https://github.com/latex3/tagging-project/issues/892
%
% Different alternatives for showing links in the text
%
\usepackage[hidelinks]{hyperref}
%\usepackage[colorlinks=true, allcolors=blue]{hyperref}
%\usepackage[colorlinks=true, linkcolor=blue, citecolor=black, urlcolor=blue]{hyperref}

\usepackage{lastpage} % To get pageref on last page for page counting
\usepackage{unicode-math} % Helps ensure the intended meaning of mathematical symbols
\usepackage{csquotes} % Partially compatible with tagging, 
                      % blockquote problematic, used to remove
                      % biblatex related warning
\usepackage{graphicx} % Required for inserting images


%%%%% Document details
\if@manual
\newcommand{\depositeplace}{}
\else
\newcommand{\depositeplace}{\translate{library}}
\fi
\newcommand{\pp}{\translate{pp}}
\newcommand{\app}{\translate{appendices}}
\newcommand{\appno}{\translate{appendice pages}}
\newcommand{\ccs}[1]{\gdef\@ccs{#1}}
\ccs{ACM Computing Classification System (CCS)}

% From document itself
\newcommand{\classification}[1]{\gdef\@classification{#1}}
\classification{\space Compulsory ACM classification missing}
\newcommand{\keywords}[1]{\gdef\@keywords{#1}}
\keywords{}
\newcommand{\additionalinformation}[1]{\gdef\@additionalinformation{#1}}

%%%%% Evaluation related elements
\newcommand{\supervisorslabel}{\translate{supervisors}}
\newcommand{\examinerlabel}{\translate{examiners}}

% From document
\newcommand{\supervisors}[1]{\gdef\@supervisors{#1}}
\newcommand{\examiners}[1]{\gdef\@examiners{#1}}

%% Date formatting
%% Numeric for Finnish and Swedish, textual for English
\if@english
\usepackage[useregional]{datetime2}
\else
\usepackage[useregional=numeric]{datetime2}
\fi

%%%%% Organisation elements
\newcommand{\uh}{\translate{uh}}
\newcommand{\address}{\translate{address}}
\newcommand{\eaddress}{\translate{eaddress}}
\newcommand{\ytiedot}{\translate{ytiedot}}
\newcommand{\helsinki}{\translate{helsinki}}
\newcommand{\faculty}{\translate{faculty}}

%% Hyperref (TOC) does not like use of translate, 
%% so these translations done separately here
\if@finnish
\newcommand{\mybibname}{Lähteet}
\newcommand{\introtitle}{Johdanto}
\newcommand{\concltitle}{Johtopäätökset}
\newcommand{\aiusetitle}{Tekoälyn käyttö tutkielmassa}

\fi
\if@swedish
\newcommand{\mybibname}{Referenser}
\newcommand{\introtitle}{Inledning}
\newcommand{\concltitle}{Slutsatser}
\newcommand{\aiusetitle}{Användning av AI i avhandlingen}

\fi
\if@english
\newcommand{\mybibname}{References}
\newcommand{\introtitle}{Introduction}
\newcommand{\concltitle}{Conclusions}
\newcommand{\aiusetitle}{Use of AI in the report}

\fi

% GENERATE TITLE PAGE

%%%%%%%%%%%%%% Cover pages
%% define first the inside of cover page, i.e., the second page
\newcommand{\innerpage}{%
\makeatletter
\label{in}
\thispagestyle{empty}
\vspace{4.0cm}
\thispagestyle{empty}
\section*{\bf \normalsize \ytiedot}

\address

\eaddress
\thispagestyle{empty}
\newpage

\thispagestyle{empty}
}

\renewcommand{\maketitle}{
\hypersetup{pageanchor=true}
\label{title}

\onehalfspacing


\pagenumbering{roman}
\begin{center}
% Translate does not seems to work in alt-text
\if@finnish
\includegraphics[alt={Helsingin yliopiston liekkimerkki Matemaattis-luonnontieteellisen tiedekunnan väreissä eli oranssina}, width=5cm]{template/figures/flame.png}
\fi
\if@swedish
\includegraphics[alt={Helsingfors universitets lågsymbol i matematisk-naturvetenskapliga fakultetens färg dvs. orange}, width=5cm]{template/figures/flame.png}
\fi
\if@english
\includegraphics[alt={The University of Helsinki flame emblem in Faculty of Science color, that is to say orange}, width=5cm]{template/figures/flame.png}
\fi


\begin{large}
\level

\programme

\end{large}

\vspace{1.7cm}


\tagpdfparaOff

\begin{LARGE}
{\bf 
\tagstructbegin{tag=H1}\tagmcbegin{tag=H1}\@title\tagmcend\tagstructend\par
}
\end{LARGE}

\tagpdfparaOn

\vspace{2cm}

\begin{large}
\@author
\end{large}

\vspace{14pt}

\begin{large}
\@date

\vspace{4cm}

\vfill

{\rm\sc
    \faculty

    \uh
}
\end{large}
\end{center}

}
\newcommand{\abstractvspace}{\vspace{0.4cm}\newline}
\newcommand{\mscabstract}[1]{
\innerpage
\thispagestyle{empty}
\setcounter{chapter}{0}
\def\abst@small{\fontsize{10}{10}\selectfont}
\def\abst@tiny{\fontsize{6}{7}\selectfont}
\section*{{\abst@small\sc HELSINGIN YLIOPISTO \hfill -- \hfill HELSINGFORS UNIVERSITET \hfill -- \hfill UNIVERSITY OF HELSINKI}}
{
\centering

% Counting the number of pages
\newcounter{apppages}
\addtocounter{apppages}{\getpagerefnumber{LastPage}}
\addtocounter{apppages}{-\getpagerefnumber{last_bib_page}}
\newcounter{mainpages}
\addtocounter{mainpages}{\getpagerefnumber{LastPage}}
\addtocounter{mainpages}{-\theapppages}

% Different language variants for pages
\newcommand{\mpinfl}{\ifnum \themainpages=1%
\translate{page}%
\else%
\translate{pages}%
\fi}
%
\newcommand{\appageinfl}{\ifnum \theapppages=1%
\translate{page}%
\else%
\translate{pages}%
\fi}

\newcommand{\pagecounts}{%
\ifnumcomp{\theapppages}{>}{0}{%
\if@finnish
   \themainpages\ \mpinfl, \theapppages\ liite\appageinfl
\else
  \if@english
    \themainpages\ \mpinfl, \theapppages\ appendix \appageinfl
   \else
    \if@swedish
       \themainpages\ \mpinfl, \theapppages\ bilaga\appageinfl
    \fi
  \fi
\fi
}{\themainpages\ \mpinfl}
}

\tagpdfsetup{table/header-rows={}} 
\begin{tabular}{|llllll|}
 \hline
 \multicolumn{3}{|p{0.47\textwidth}|}{{\abst@tiny Tiedekunta --- Fakultet --- Faculty}\abstractvspace\abst@small \faculty} & \multicolumn{3}{p{0.47\textwidth}|}{{\abst@tiny \oppiaine} \abstractvspace\abst@small \getSubject} \\
 \hline
 \multicolumn{6}{|p{0.94\textwidth}|}{{\abst@tiny Tekijä --- Författare --- Author}\abstractvspace\abst@small \@author} \\
 \hline
 \multicolumn{6}{|p{0.94\textwidth}|}{{\abst@tiny Työn nimi --- Arbetets titel --- Title}\abstractvspace\abst@small \@title} \\
 \hline
 \multicolumn{6}{|p{0.94\textwidth}|}{{\abst@tiny Ohjaaja(t) --- Handledare --- Supervisor(s)}\abstractvspace\abst@small \@supervisors} \\
 \hline
 \multicolumn{2}{|p{0.305\textwidth}|}{{\abst@tiny Työn laji --- Arbetets art --- Level}\abstractvspace\abst@small \level} & 
 \multicolumn{2}{p{0.305\textwidth}|}{{\abst@tiny Aika --- Datum --- Date }\abstractvspace\abst@small \@date} 
 & \multicolumn{2}{p{0.305\textwidth}|}{{\abst@tiny Sivumäärä --- Sidoantal ---    Number of pages}\abstractvspace\abst@small\pagecounts}\\
 \hline
 \multicolumn{6}{|p{0.94\textwidth}|}{{\abst@tiny Tiivistelmä --- Sammanfattning --- Abstract}
\abst@small
\begin{center}
\begin{minipage}[t][9.4cm][t]{0.9\textwidth}
\setlength{\parskip}{0.7\baselineskip}
#1

\vfill

\begin{otherlanguage}{english}\textbf{ACM Computing Classification System (CCS)} 
\@classification\end{otherlanguage}

\vspace{1.2\baselineskip}
\end{minipage}\end{center}}\\
 \hline
 \multicolumn{6}{|p{0.94\textwidth}|}{{\abst@tiny Avainsanat --- Nyckelord --- Keywords}\abstractvspace\abst@small\@keywords} \\ 
 \hline
 \multicolumn{6}{|p{0.94\textwidth}|}{{\abst@tiny Säilytyspaikka --- Förvaringsställe --- Where deposited} \abstractvspace\abst@small\depositeplace} \\
 \hline
 \multicolumn{6}{|p{0.94\textwidth}|}{{\abst@tiny Muita tietoja --- Övriga uppgifter --- Additional information} \abstractvspace\abst@small \@additionalinformation} \\
 \hline
\end{tabular}
}
\thispagestyle{empty}
}

% Fixing url-date to Finnish-Swedish dd.mm.yyy instead of Swedish one
% and prettier DOIs in bibliography
\AtBeginDocument{%
\DeclareFieldFormat{doi}{%   
\mkbibacro{DOI}\addcolon\space   
\ifhyperref     
{\href{https://doi.org/#1}{\nolinkurl{#1}}}     
{\nolinkurl{#1}}}
  %  
  \DefineBibliographyExtras{swedish}{%
    \DeclareFieldFormat{urldate}{%
      \iffieldundef{urlyear}
        {}
        {Hämtad \stripzeros{\thefield{urlday}}\adddot
         \stripzeros{\thefield{urlmonth}}\adddot
         \thefield{urlyear} från}%
    }%
}
 %  
 \DefineBibliographyExtras{english}{%
    \DeclareFieldFormat{urldate}{%
      \iffieldundef{urlyear}
        {}
        {Retrieved \stripzeros{\thefield{urlday}}\adddot
         \stripzeros{\thefield{urlmonth}}\adddot
         \thefield{urlyear} from}%
    }%
}
 \DefineBibliographyExtras{english}{%
    \DeclareFieldFormat{url}{%
      \iffieldundef{url}
        {}
        {\thefield{url}\adddot}%
    }%
}
 \DefineBibliographyExtras{finnish}{%
    \DeclareFieldFormat{url}{%
      \iffieldundef{url}
        {}
        {\thefield{url}\adddot}%
    }%
} \DefineBibliographyExtras{swedish}{%
    \DeclareFieldFormat{url}{%
      \iffieldundef{url}
        {}
        {\thefield{url}\adddot}%
    }%
}
}

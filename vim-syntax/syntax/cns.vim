" File:        cns.vim
" Author:      Chris Smeele
" Version:     0.1
" Description: Syntax rules for CNS files with CNSParser features

if exists("b:current_syntax")
	finish
endif

syn case ignore

" These patterns may be too strict or too basic, but using them enforces consistency.

" ToDo: Match boolean values and choice attributes

syn match  cnsComment   "^![^#]*"
syn match  cnsComment   "{[=!*]\@!.*}"
syn match  cnsAccesslevelDef   "^\s*{!accesslevel\s\+[a-z0-9A-Z_]\+\s\+\S.*}" contains=cnsAccessLevelKW,cnsAccesslevelName,cnsAccesslevelLabel
syn match  cnsAccesslevelKW    "\(^\s*{!\)\@<=accesslevel" contained
syn match  cnsAccesslevelName  "\(^\s*{!accesslevel\s\+\)\@<=[a-z0-9A-Z_]\+" contained
syn match  cnsAccesslevelLabel "\(^\s*{!accesslevel\s\+[a-z0-9A-Z_]\+\s\+\)\@<=\"[^\"]*\"\+" contained

"syn region cnsHeader    start="^\s*{==\+" end="==\+}"
syn match  cnsHeader    "^\s*{==\+.*==\+}"
syn match  cnsParagraph "\(^\s*{\*\s*\)\@<=.\{-}\(\s*\*}\)\@="

syn region cnsAttributes     start="\(^\s*![^#]*\)\@<=#" end="$"       contains=cnsAttribute
syn match  cnsAttribute      "#[a-zA-Z_-]\+\([=:]\S\+\)\="   contained contains=cnsAttributeName,cnsAttributeValue
syn match  cnsAttributeName  "#\@<=[a-zA-Z_-]\+"             contained
syn match  cnsAttributeValue "\(#[a-zA-Z_-]\+[=:]\)\@<=\S\+" contained contains=cnsString,cnsNumber

syn match  cnsAssignment "\(^\s*\({===>}\s*\)\=\)[a-zA-Z0-9_]\+\s*=\s*\S.*;" contains=cnsParameter,cnsValue
syn match  cnsParameter  "\(^\s*\({===>}\s*\)\=\)\@<=[a-zA-Z0-9_]\+" contained
syn match  cnsValue      "\(^\s*\({===>}\s*\)\=[a-zA-Z0-9_]\+\s*=\s*\)\@<=.*\(;\)\@=" contained contains=cnsString,cnsNumber

syn region cnsString start="\"" end="\"" contained
syn match  cnsNumber "\<\d\+\>"          contained
syn match  cnsNumber "\<\d*\.\d\+\>"     contained


hi def link cnsComment Comment

hi def link cnsAccesslevelKW    Keyword
hi def link cnsAccesslevelName  Identifier
hi def link cnsAccesslevelLabel String

hi def link cnsHeader    Special
hi def link cnsParagraph String

hi def link cnsAttributeName Keyword

hi def link cnsParameter Identifier

hi def link cnsString    String
hi def link cnsNumber    Number


let b:current_syntax = "cns"

#= 

ooo        ooooo   .oooooo.   oooooooooo.   oooooooooooo ooooo                   .o.       
`88.       .888'  d8P'  `Y8b  `888'   `Y8b  `888'     `8 `888'                  .888.      
 888b     d'888  888      888  888      888  888          888                  .8"888.     
 8 Y88. .P  888  888      888  888      888  888oooo8     888                 .8' `888.    
 8  `888'   888  888      888  888      888  888    "     888                .88ooo8888.   
 8    Y     888  `88b    d88'  888     d88'  888       o  888       o       .8'     `888.  
o8o        o888o  `Y8bood8P'  o888bood8P'   o888ooooood8 o888ooooood8      o88o     o8888o 

=# 

cd(@__DIR__)

using Distributions
using Printf
using Random
using JLD2
using CodecZlib

include("initialize.jl")
include("simulation.jl")

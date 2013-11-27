#/bin/bash
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# Written (W) 2009-2013 Andre Kahles, Jonas Behr, Gunnar Raetsch
# Copyright (C) 2009-2011 Max Planck Society
# Copyright (C) 2012-2013 Memorial Sloan-Kettering Cancer Center
#
# SplAdder wrapper script to start the interpreter with the correct list of arguments

set -e


function usage () {
    echo "
    
    Usage: SplAdder [-OPTION VALUE] 

    Options:
    "

    exit 0
}

[[ -z "$1" ]] && usage

### init default parameters
S_BAM_FNAME=""
S_OUT_DIRNAME="."
S_LOG_FNAME=""
S_ANNO_FNAME=""
S_USER_FNAME=""
S_MERGE_STRATEGY="merge_bams" ## alternatives are: merge_graphs, single
S_EXPERIMENT_LABEL="-"
S_REFERENCE_STRAIN="-"
I_CONFIDENCE="3"
I_INSERT_IR="1"
I_INSERT_CE="1"
I_INSERT_IE="1"
I_REMOVE_SE="0"
I_INFER_SG="0"
I_INSERT_INTRON_ITER="5"
I_VERBOSE="0"
I_DEBUG="0"
I_RPROC="0"
I_VALIDATE_SG="0"
I_SHARE_GENESTRUCT="0"
I_CURATE_ALTPRIME="0"


### parse parameters from command lines
while getopts "b:o:l:a:u:c:I:M:R:L:S:dpVvAxieErsh" opt
do
    case $opt in
    b ) S_BAM_FNAME="$OPTARG" ;;
    o ) S_OUT_DIRNAME="$OPTARG" ;;
    l ) S_LOG_FNAME="$OPTARG" ;;
    a ) S_ANNO_FNAME="$OPTARG" ;;
    u ) S_USER_FNAME="$OPTARG" ;;
    c ) I_CONFIDENCE="$OPTARG" ;;
    I ) I_INSERT_INTRON_ITER="$OPTARG" ;;
    M ) S_MERGE_STRATEGY="$OPTARG" ;;
    R ) S_REPLICATE_IDX="$OPTARG" ;;
    L ) S_EXPERIMENT_LABEL="$OPTARG" ;;
    S ) S_REFERENCE_STRAIN="$OPTARG" ;;
    d ) I_DEBUG="1" ;;
    p ) I_RPROC="1" ;;
    V ) I_VALIDATE_SG="1" ;;
    v ) I_VERBOSE="1" ;;
    A ) I_CURATE_ALTPRIME="1" ;;
    x ) I_SHARE_GENESTRUCT="1" ;;
    i ) I_INSERT_IR="0" ;;
    e ) I_INSERT_CE="0" ;;
    E ) I_INSERT_IE="0" ;;
    r ) I_REMOVE_SE="1" ;;
    s ) I_INFER_SG="1" ;;
    h ) usage ;;
    \?) echo -e "UNKNOWN PARAMETER: $opt\n\n"; usage ;;
    esac
done

### assemble parameter string
PARAMS=""
for opt in S_BAM_FNAME S_OUT_DIRNAME S_LOG_FNAME S_ANNO_FNAME S_USER_FNAME I_CONFIDENCE I_INSERT_INTRON_ITER I_DEBUG I_VERBOSE I_INSERT_IR I_INSERT_CE I_INSERT_IE I_REMOVE_SE I_INFER_SG I_VALIDATE_SG S_MERGE_STRATEGY I_SHARE_GENESTRUCT S_REPLICATE_IDX S_EXPERIMENT_LABEL S_REFERENCE_STRAIN I_CURATE_ALTPRIME I_RPROC 
do
    eval "PARAMS=\"$PARAMS${opt}:\${$opt};\""
done

### Index Bam files
echo "Indexing BAM files"
SAMPLE_LIST=()
IFS=',' 
for BAM_FILE in "${S_BAM_FNAME}"
do
    CURR_BAMFILE=$BAM_FILE
    if [ ! -f ${CURR_BAMFILE}.bai ]
    then
        echo "Indexing $CURR_BAMFILE"
        ${SPLADDER_SAMTOOLS_BIN_DIR} index $BAM_FILE
    else
        echo "$CURR_BAMFILE already indexed"
    fi
done
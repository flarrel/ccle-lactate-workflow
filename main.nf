nextflow.enable.dsl=2

process PREPARE {
    publishDir params.outdir, mode: 'copy', pattern: 'qc.json'

    input:
    path code
    path expression
    path mutations
    path metadata
    path metabolites

    output:
    path 'cohort.csv', emit: cohort
    path 'qc.json', emit: qc

    script:
    """
    "${params.python}" "$code" "$expression" "$mutations" "$metadata" "$metabolites"
    """
}

process REGRESS {
    publishDir params.outdir, mode: 'copy'

    input:
    path code
    path cohort
    path qc

    output:
    path 'model.json', emit: metrics
    path 'predictions.csv'

    script:
    """
    OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 OMP_NUM_THREADS=1 "${params.python}" "$code" "$cohort" "$qc"
    """
}

process SIMULATE {
    publishDir params.outdir, mode: 'copy'

    input:
    path code

    output:
    path 'pathway.json', emit: metrics
    path 'pathway.csv'

    script:
    """
    "${params.python}" "$code"
    """
}

process EVIDENCE {
    publishDir params.outdir, mode: 'copy'

    input:
    path code
    path sources
    path questions
    path model
    val executable
    path qc
    path regression
    path pathway

    output:
    path 'evidence.json'
    path 'answers.jsonl'
    path 'retained_sources.json'

    script:
    """
    "${params.python}" "$code" "$sources" "$questions" "$model" "$executable" "$qc" "$regression" "$pathway"
    """
}

workflow {
    def root = file(params.data_dir)
    prepared = PREPARE(
        file("${projectDir}/src/prepare.py"),
        file("${root}/CCLE_expression.csv", checkIfExists: true),
        file("${root}/CCLE_mutations.csv", checkIfExists: true),
        file("${root}/sample_info.csv", checkIfExists: true),
        file("${root}/metabolomics.xlsx", checkIfExists: true)
    )
    regression = REGRESS(file("${projectDir}/src/analysis.py"), prepared.cohort, prepared.qc)
    pathway = SIMULATE(file("${projectDir}/src/pathway.py"))
    EVIDENCE(
        file("${projectDir}/src/research.py"),
        file("${projectDir}/evidence/sources.json"),
        file("${projectDir}/evidence/questions.json"),
        file("${root}/${params.model_name}", checkIfExists: true),
        params.llama,
        prepared.qc,
        regression.metrics,
        pathway.metrics
    )
}

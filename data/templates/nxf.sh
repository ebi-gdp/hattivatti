nextflow run pgscatalog/pgsc_calc -profile test,singularity \
         -c ${HATTIVATTI_WORK_DIR}/{name}/config \
         -c ${HATTIVATTI_WORK_DIR}/allas.config \
         --input ${HATTIVATTI_WORK_DIR}/{name}/input.json \
         --min_overlap 0.01 \
         --max_cpus 40 \
         --max_memory "32.GB" \
         --parallel

#!/usr/bin/env python

import os, sys, re, shutil
import subprocess, multiprocessing, logging
from Bio import SeqIO
from optparse import OptionParser

__doc__ = """
Script to run qiime-uclust (search mode - no clustering) in parallel.
Splits input fasta_file and runs parts on seperate cpus.
Output is fasta file of input hits against library."""

id_re  = re.compile('^(\S+)\t')
fa_re  = re.compile('^>')
LIBF   = ''
INFF   = ''
IDENT  = 0.9
TMPDIR = None

def run_cmd(cmd):
    proc = subprocess.Popen( cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        raise IOError("%s\n%s"%(" ".join(cmd), stderr))
    return stdout, stderr

def write_file(text, file, append):
    if append:
        mode = 'a'
    else:
        mode = 'w'
    outhdl = open(file, mode)
    outhdl.write(text)
    outhdl.close()

def split_fasta(infile, bytes):
    num   = 1
    char  = 0
    text  = ''
    files = []
    fname = os.path.join(TMPDIR, os.path.basename(infile))
    inhdl = open(infile, "rU")
    for line in inhdl:
        head = fa_re.match(line)
        if head and (char >= (bytes * 1024 * 1024)):
            files.append("%s.%d"%(fname, num))
            write_file(text, "%s.%d"%(fname, num), 0)
            num += 1
            char = 0
            text = ''
        text += line
        char += len(line)
    if text != '':
        files.append("%s.%d"%(fname, num))
        write_file(text, "%s.%d"%(fname, num), 0)
    inhdl.close()
    return files

def run_search(fname):
    runtmp = os.path.join(TMPDIR, 'tmp.'+os.path.basename(fname))
    os.mkdir(runtmp)
    sortf = fname + '.sort'
    srchf = fname + '.uc'
    outf  = srchf + '.fa'
    cmd1  = ['qiime-uclust', '--sort', fname, '--output', sortf, '--tmpdir', runtmp]
    cmd2  = ['usearch', '--query', sortf, '--db', LIBF, '--uc', srchf, '--id', str(IDENT), '--rev']
    cmd3  = ['qiime-uclust', '--input', sortf, '--uc2fasta', srchf, '--output', outf, '--types', 'H', '--origheader', '--tmpdir', runtmp]
    so1, se1 = run_cmd(cmd1)
    so2, se2 = run_cmd(cmd2)
    so3, se3 = run_cmd(cmd3)
    write_file("".join([so1,se1,so2,se2,so3,se3]), outf+".log", 1)
    os.remove(sortf)
    os.remove(srchf)
    shutil.rmtree(runtmp)
    return outf

def merge_files(files, outfile, logfile):
    if logfile:
        log_files = map( lambda x: "%s.log"%x, files )
        os.system( "cat %s > %s"%( " ".join(log_files), logfile ) )
    os.system( "cat %s > %s"%( " ".join(files), outfile ) )
    return
    
usage = "usage: %prog [options] library_fasta input_fasta output_fasta\n" + __doc__

def main(args):
    global LIBF, INFF, IDENT, TMPDIR
    parser = OptionParser(usage=usage)
    parser.add_option("-p", "--processes", dest="processes", metavar="NUM_PROCESSES", type="int", default=4, help="Number of processes to use [default '4']")
    parser.add_option("-s", "--byte_size", dest="size", metavar="BYTE_SIZE", type="int", default=100, help="Byte size to split fasta file (in MB) [default '100']")
    parser.add_option("-i", "--identity", dest="identity", metavar="IDENTITY", type="float", default=0.9, help="Identity score for uclust match [default '%f']"%IDENT)
    parser.add_option("-d", "--tmp_dir", dest="tmpdir", metavar="DIR", default="/tmp", help="DIR for intermediate files (must be full path), deleted at end [default '/tmp']")
    parser.add_option("-l", "--log_file", dest="logfile", metavar="FILE", default=None, help="File of concatenated search log text. [default is '/dev/null']")
    parser.add_option("-v", "--verbose", dest="verbose", action="store_true", default=False, help="Wordy [default is off]")
    
    (opts, args) = parser.parse_args()
    if len(args) != 3:
        parser.print_help()
        print "[error] incorrect number of arguments"
        return 1
    if not os.path.isdir(opts.tmpdir):
        parser.print_help()
        print "[error] invalid tmpdir"
        return 1

    (LIBF, INFF, out_f) = args
    IDENT  = opts.identity
    TMPDIR = opts.tmpdir

    if opts.verbose: sys.stdout.write("Splitting file %s ... "%INFF)
    sfiles = split_fasta(INFF, opts.size)
    scount = len(sfiles)
    if opts.verbose: sys.stdout.write("Done - %d splits\n%s\n"%(scount, "\n".join(sfiles)))

    if scount < opts.processes:
        min_proc = scount
    else:
        min_proc = opts.processes

    if opts.verbose: sys.stdout.write("search using %d threades ... "%min_proc)        
    pool   = multiprocessing.Pool(processes=min_proc)
    rfiles = pool.map(run_search, sfiles, 1)
    pool.close()
    pool.join()
    if opts.verbose: sys.stdout.write("Done - %d splits\n%s\n"%(len(rfiles), "\n".join(rfiles)))

    if opts.verbose: sys.stdout.write("Merging %d outputs ... "%len(rfiles))
    merge_files(rfiles, out_f, opts.logfile)
    if opts.verbose: sys.stdout.write("Done\n")

    if opts.verbose: sys.stdout.write("Deleting intermediate files ... ")
    for f in sfiles: os.remove(f)
    for f in rfiles: os.remove(f)
    for f in rfiles: os.remove(f+'.log')
    if opts.verbose: sys.stdout.write("Done\n")
    
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))

from lxml import etree

def roundtrip_xml_lxml(input_path: str, output_path: str, target_tag: str):
    """
    reads an xml with low memory consumption and writes incrementally
    target_tag should be used to specify a particular tag one is interested in
    """

    # iterparse for the input (only 'end' events are necessary)
    # ideal for a flat hierarchy with a high number of repeating xml elements
    context = etree.iterparse(input_path, events=('end',), tag=target_tag)
    
    # context manager to write the output stream
    with etree.xmlfile(output_path, encoding='utf-8') as xf:
        
        # opening root tag (here called 'Root', could also be parsed from the input)
        with xf.element('Root'):
            
            for event, elem in context:
                # ---------------------------------------------------
                # add modifications here
                # ---------------------------------------------------
                
                # write element to file
                xf.write(elem)
                
                # clear memory for this element
                elem.clear()
                
                # by default the parser stores parent child relations
                # delete processed siblings
                while elem.getprevious() is not None:
                    del elem.getparent()[0]
